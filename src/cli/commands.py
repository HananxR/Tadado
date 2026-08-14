"""Command executors — pure logic over TaskService + AppConfig.

Shared by both execution paths: headless (own process) and forwarded
(executed inside the running GUI via the local pipe).  Every handler
returns a plain JSON-serializable dict; errors raise :class:`CliError`.
"""

from __future__ import annotations

import logging
import re as _re
from datetime import date, timedelta
from pathlib import Path

from ..models.task import Task
from ..models.task_filter import SortCriterion, TaskFilter
from ..models.task_status import TaskStatus
from ..services.md_exporter import MarkdownExporter
from ..services.md_formatter import MarkdownTaskFormatter
from ..services.task_exporter import export_xlsx
from .output import task_to_dict

_log = logging.getLogger("runlog")

_STATUS_VALUES = {s.value for s in TaskStatus}


class CliError(Exception):
    """User-facing CLI error with an exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def execute(command: str, args, svc, config=None) -> dict:
    """Dispatch ``command`` with parsed ``args`` against the service seam."""
    handler = _HANDLERS.get(command)
    if handler is None:
        raise CliError(f"未知命令: {command}")
    return handler(args, svc, config)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise CliError(f"日期格式无效: {raw!r}（应为 YYYY-MM-DD）") from exc


def _parse_due_arg(raw: str) -> tuple[date, str | None]:
    """Parse 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM'."""
    parts = raw.strip().replace("T", " ", 1).split(" ", 1)
    return _parse_date(parts[0]), (parts[1] if len(parts) > 1 else None)


def _parse_tags_arg(raw: str) -> list[str]:
    return [t.strip().lstrip("#") for t in raw.split(",") if t.strip()]


def _statuses_from(values: list[str] | None) -> set[TaskStatus] | None:
    if not values:
        return None
    for v in values:
        if v.upper() not in _STATUS_VALUES:
            raise CliError(f"无效状态: {v!r}（可选 {sorted(_STATUS_VALUES)}）")
    return {TaskStatus.from_string(v) for v in values}


def _build_filter(args) -> TaskFilter:
    """Map list-command args onto a TaskFilter."""
    return TaskFilter(
        search_text=args.keyword or "",
        statuses=_statuses_from(getattr(args, "status", None)),
        tags=set(args.tag) if getattr(args, "tag", None) else None,
        partition_id=args.partition or None,
        date_from=_parse_date(args.date_from) if args.date_from else None,
        date_to=_parse_date(args.date_to) if args.date_to else None,
        overdue_only=bool(getattr(args, "overdue", False)),
        show_archived=bool(getattr(args, "archived", False)),
        urgencies={args.urgency} if args.urgency is not None else None,
        sort_by=[SortCriterion(args.sort, ascending=not args.desc)],
        limit=args.limit,
        offset=args.offset,
    )


def _resolve_ids(args, svc) -> list[str]:
    """Resolve positional ids + --match into a verified task-id list."""
    ids = list(getattr(args, "ids", None) or [])
    match = getattr(args, "match", None)
    if match:
        candidates = svc.search(TaskFilter(search_text=match, show_archived=True))
        if not candidates:
            raise CliError(f"未找到匹配 {match!r} 的任务")
        if len(candidates) > 1:
            listing = "；".join(f"{t.id[:8]} {t.title}" for t in candidates[:8])
            raise CliError(f"匹配到多个任务，请用 ID 指定：{listing}")
        ids.append(candidates[0].id)
    if not ids:
        raise CliError("需要任务 ID 或 --match 关键词")
    verified: list[str] = []
    for task_id in ids:
        if svc.get_task(task_id) is None:
            raise CliError(f"任务不存在: {task_id}")
        if task_id not in verified:
            verified.append(task_id)
    return verified


def _load_one(args, svc) -> Task:
    ids = _resolve_ids(args, svc)
    if len(ids) > 1:
        raise CliError("该命令一次只能操作一个任务")
    return svc.get_task(ids[0])


def _with_names(svc, tasks: list[Task]) -> list[dict]:
    name_map = svc.get_partition_name_map()
    return [task_to_dict(t, name_map.get(t.partition_id or "", "")) for t in tasks]


def _md_with_status(status: TaskStatus, md_line: str) -> str:
    """Inject a non-TODO status keyword after the checkbox bracket."""
    if status == TaskStatus.TODO:
        return md_line
    return md_line.replace("] ", f"] {status.value} ", 1)


# ------------------------------------------------------------------
# list / today
# ------------------------------------------------------------------

def _cmd_list(args, svc, config) -> dict:
    f = _build_filter(args)
    total = svc.count(f)
    tasks = svc.search(f)
    return {
        "type": "task_list",
        "count": len(tasks),
        "total": total,
        "tasks": _with_names(svc, tasks),
    }


def _cmd_today(args, svc, config) -> dict:
    today = date.today()
    horizon = today + timedelta(days=args.days)
    name_map = svc.get_partition_name_map()
    groups: dict[str, list[dict]] = {
        "overdue": [], "due_today": [], "due_soon": [], "doing": [],
    }
    for t in svc.get_all():
        if t.archived or t.suspended or t.status == TaskStatus.DONE:
            continue
        d = task_to_dict(t, name_map.get(t.partition_id or "", ""))
        if t.deadline_date:
            if t.deadline_date < today:
                groups["overdue"].append(d)
            elif t.deadline_date == today:
                groups["due_today"].append(d)
            elif t.deadline_date <= horizon:
                groups["due_soon"].append(d)
        elif t.status == TaskStatus.DOING:
            groups["doing"].append(d)
    for group in groups.values():
        group.sort(key=lambda d: (d["urgency"], d.get("deadline_date") or "9999"))
    return {
        "type": "today",
        "date": today.isoformat(),
        "days": args.days,
        "overdue": groups["overdue"],
        "due_today": groups["due_today"],
        "due_soon": groups["due_soon"],
        "doing": groups["doing"],
    }


# ------------------------------------------------------------------
# add / edit / done / rm
# ------------------------------------------------------------------

def _cmd_add(args, svc, config) -> dict:
    md = (args.markdown or "").strip()
    # Normalize "TODO<date>" → "TODO <date>" so LLM-generated lines without
    # the canonical space after the status keyword parse correctly.
    md = _re.sub(r"((?:TODO|DOING|DONE|OVERDUE))\s*(?=<)", r"\1 ", md, flags=_re.IGNORECASE)
    parsed = svc.parse_markdown(md) if md else None

    title = args.title or (parsed.title if parsed else "")
    if not title:
        raise CliError("add 需要任务文本（Markdown 行）或 --title")
    status = TaskStatus.from_string(args.status) if args.status else (
        parsed.status if parsed else TaskStatus.TODO
    )
    if args.status and args.status.upper() not in _STATUS_VALUES:
        raise CliError(f"无效状态: {args.status!r}")
    if args.due:
        due, due_time = _parse_due_arg(args.due)
    else:
        due = parsed.deadline_date if parsed else None
        due_time = parsed.deadline_time if parsed else None
    if args.scheduled:
        scheduled = _parse_date(args.scheduled)
    else:
        scheduled = parsed.scheduled_date if parsed else None
    tags = _parse_tags_arg(args.tags) if args.tags is not None else (
        parsed.tags if parsed else []
    )
    urgency = args.urgency if args.urgency is not None else (
        parsed.urgency if parsed else 3
    )

    md_line = MarkdownTaskFormatter.format_fields(
        scheduled_date=scheduled.isoformat() if scheduled else None,
        deadline_date=due.isoformat() if due else None,
        deadline_time=due_time,
        title=title,
        tags=tags,
        urgency=urgency,
    )
    md_line = _md_with_status(status, md_line)

    partition_id = args.partition or svc.ensure_default_partition()
    task = svc.create_task(md_line, partition_id)
    if args.notes is not None or args.recur is not None:
        if args.notes is not None:
            task.notes = args.notes
        if args.recur is not None:
            task.recurrence_rule = args.recur
        task = svc.update_task(task)
    name_map = svc.get_partition_name_map()
    return {"type": "task", "task": task_to_dict(task, name_map.get(task.partition_id or "", ""))}


def _cmd_edit(args, svc, config) -> dict:
    task = _load_one(args, svc)
    old_md = task.raw_md
    status_target = TaskStatus.from_string(args.status) if args.status else None
    field_changed = False

    if args.title is not None:
        task.title, field_changed = args.title, True
    if args.due is not None:
        task.deadline_date, task.deadline_time = _parse_due_arg(args.due)
        field_changed = True
    if args.clear_due:
        task.deadline_date, task.deadline_time = None, None
        field_changed = True
    if args.scheduled is not None:
        task.scheduled_date = _parse_date(args.scheduled)
        field_changed = True
    if args.clear_scheduled:
        task.scheduled_date = None
        field_changed = True
    if args.tags is not None:
        task.tags = _parse_tags_arg(args.tags)
        field_changed = True
    if args.urgency is not None:
        task.urgency = args.urgency
        field_changed = True
    if args.notes is not None:
        task.notes = args.notes
        field_changed = True
    if args.recur is not None:
        task.recurrence_rule = args.recur or None
        field_changed = True
    if args.partition is not None:
        task.partition_id = args.partition
        field_changed = True

    new_md = svc.format_task(task)
    changes = []
    if field_changed:
        changes.append(f"更新字段（{old_md} → {new_md}）")
    if status_target is not None and status_target != task.status:
        changes.append(f"状态 {task.status.value} → {status_target.value}")
    if not changes:
        raise CliError("未提供任何要修改的字段")
    if args.dry_run:
        return {
            "type": "dry_run", "command": "edit", "task_id": task.id,
            "changes": changes, "before": old_md, "after": new_md,
        }

    if field_changed:
        task = svc.update_task(task)
    if status_target is not None and status_target != task.status:
        task = svc.change_task_status(task, status_target)
    name_map = svc.get_partition_name_map()
    return {"type": "task", "task": task_to_dict(task, name_map.get(task.partition_id or "", ""))}


def _cmd_done(args, svc, config) -> dict:
    ids = _resolve_ids(args, svc)
    target = TaskStatus.from_string(args.status) if args.status else TaskStatus.DONE
    if args.status and args.status.upper() not in _STATUS_VALUES:
        raise CliError(f"无效状态: {args.status!r}")
    preview = []
    for task_id in ids:
        t = svc.get_task(task_id)
        preview.append({"id": t.id, "title": t.title,
                        "from": t.status.value, "to": target.value})
    if args.dry_run:
        return {"type": "dry_run", "command": "done", "changes": preview}
    for task_id in ids:
        svc.change_task_status(svc.get_task(task_id), target)
    return {"type": "status_change", "count": len(ids), "status": target.value, "ids": ids}


def _cmd_rm(args, svc, config) -> dict:
    ids = _resolve_ids(args, svc)
    if args.dry_run:
        preview = [{"id": svc.get_task(i).id, "title": svc.get_task(i).title}
                   for i in ids]
        return {"type": "dry_run", "command": "rm", "changes": preview}
    svc.batch_delete(ids)
    return {"type": "deleted", "count": len(ids), "ids": ids}


# ------------------------------------------------------------------
# tags / partitions
# ------------------------------------------------------------------

def _cmd_tags(args, svc, config) -> dict:
    pid = args.partition or None
    if args.counts:
        entries = [{"tag": t, "count": c} for t, c in svc.get_all_tags_with_counts(pid)]
        return {"type": "tags", "tags": entries}
    return {"type": "tags", "tags": svc.get_all_tags(pid)}


def _partition_dict(p: dict, svc) -> dict:
    has_password, _ = svc.check_partition_password(p["id"])
    return {
        "id": p["id"],
        "name": p["name"],
        "sort_order": p.get("sort_order"),
        "archive_days": p.get("archive_days"),
        "task_count": svc.count_tasks_in_partition(p["id"]),
        "has_password": bool(has_password),
    }


def _cmd_partitions(args, svc, config) -> dict:
    if args.add:
        p = svc.upsert_partition(args.add)
        return {"type": "partition", "partition": _partition_dict(p, svc)}
    if args.rename:
        pid, name = args.rename
        if svc.get_partition_name_map().get(pid) is None:
            raise CliError(f"分区不存在: {pid}")
        p = svc.upsert_partition(name, partition_id=pid)
        return {"type": "partition", "partition": _partition_dict(p, svc)}
    if args.rm:
        if svc.get_partition_name_map().get(args.rm) is None:
            raise CliError(f"分区不存在: {args.rm}")
        svc.delete_partition(args.rm)
        return {"type": "partition_deleted", "id": args.rm}
    parts = [_partition_dict(p, svc) for p in svc.get_all_partitions()]
    return {"type": "partition_list", "partitions": parts}


# ------------------------------------------------------------------
# archive / recurrence / reminder / export
# ------------------------------------------------------------------

def _cmd_archive(args, svc, config) -> dict:
    if args.all:
        tasks = svc.search(TaskFilter(statuses={TaskStatus.DONE}, show_archived=False))
        ids = [t.id for t in tasks]
    else:
        ids = _resolve_ids(args, svc)
    if args.dry_run:
        preview = [{"id": svc.get_task(i).id, "title": svc.get_task(i).title}
                   for i in ids]
        return {"type": "dry_run", "command": "archive", "changes": preview}
    svc.archive_batch(ids)
    return {"type": "archived", "count": len(ids), "ids": ids}


def _cmd_recurrence(args, svc, config) -> dict:
    task = _load_one(args, svc)
    if not args.rule:
        return {"type": "recurrence", "task_id": task.id, "rule": task.recurrence_rule}
    task.recurrence_rule = args.rule
    svc.update_task(task)
    return {"type": "recurrence", "task_id": task.id, "rule": task.recurrence_rule}


def _cmd_reminder(args, svc, config) -> dict:
    if config is None:
        raise CliError("reminder 命令需要配置支持")
    changed = False
    if args.enable:
        config.set("reminders", "enabled", value=True)
        changed = True
    if args.disable:
        config.set("reminders", "enabled", value=False)
        changed = True
    if args.digest_time:
        config.set("reminders", "daily_digest_time", value=args.digest_time)
        changed = True
    if args.quiet_start:
        config.set("reminders", "quiet_hours_start", value=args.quiet_start)
        changed = True
    if args.quiet_end:
        config.set("reminders", "quiet_hours_end", value=args.quiet_end)
        changed = True
    if changed:
        config.save()
    return {
        "type": "reminder",
        "enabled": bool(config.reminders_enabled),
        "daily_digest_time": config.reminder_daily_digest_time,
        "quiet_hours_start": config.get("reminders", "quiet_hours_start") or "22:00",
        "quiet_hours_end": config.get("reminders", "quiet_hours_end") or "08:00",
    }


def _cmd_export(args, svc, config) -> dict:
    f = TaskFilter(partition_id=args.partition or None, show_archived=True)
    tasks = svc.search(f)
    fmt = args.fmt or "md"
    out = Path(args.out) if args.out else Path(f"tadado_tasks.{fmt}")
    out = out.resolve()
    if fmt == "md":
        MarkdownExporter.export_to_file(tasks, str(out))
    elif fmt == "xlsx":
        export_xlsx(tasks, str(out))
    else:
        raise CliError(f"不支持的导出格式: {fmt!r}（可选 md/xlsx）")
    return {"type": "export", "format": fmt, "path": str(out), "count": len(tasks)}


_HANDLERS = {
    "list": _cmd_list,
    "today": _cmd_today,
    "add": _cmd_add,
    "edit": _cmd_edit,
    "done": _cmd_done,
    "rm": _cmd_rm,
    "tags": _cmd_tags,
    "partitions": _cmd_partitions,
    "archive": _cmd_archive,
    "recurrence": _cmd_recurrence,
    "reminder": _cmd_reminder,
    "export": _cmd_export,
}

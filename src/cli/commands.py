"""Command executors — pure logic over TaskService + AppConfig.

Shared by both execution paths: headless (own process) and forwarded
(executed inside the running GUI via the local pipe).  Every handler
returns a plain JSON-serializable dict; errors raise :class:`CliError`.
"""

from __future__ import annotations

import logging
import re as _re
from datetime import date, datetime, timedelta
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


def _build_filter(args, svc) -> TaskFilter:
    """Map list-command args onto a TaskFilter."""
    return TaskFilter(
        search_text=args.keyword or "",
        statuses=_statuses_from(getattr(args, "status", None)),
        tags=set(args.tag) if getattr(args, "tag", None) else None,
        partition_id=_resolve_partition_id(svc, args.partition) if args.partition else None,
        date_from=_parse_date(args.date_from) if args.date_from else None,
        date_to=_parse_date(args.date_to) if args.date_to else None,
        overdue_only=bool(getattr(args, "overdue", False)),
        show_archived=bool(getattr(args, "archived", False)),
        urgencies={args.urgency} if args.urgency is not None else None,
        sort_by=[SortCriterion(args.sort, ascending=not args.desc)],
        limit=args.limit,
        offset=args.offset,
    )


def _resolve_id_prefix(value: str, ids: list[str], kind: str) -> str | None:
    """Exact match wins; otherwise a unique prefix (>=8 chars) resolves.

    Raises CliError when a prefix is ambiguous.
    """
    if value in ids:
        return value
    matches = [i for i in ids if i.startswith(value)] if len(value) >= 8 else []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise CliError(f"{kind} ID 前缀 {value!r} 匹配到多个，请提供更长的 ID")
    return None


def _resolve_partition_id(svc, value: str) -> str:
    """Resolve a partition by id, unique prefix (>=8 chars), or exact name."""
    name_map = svc.get_partition_name_map()
    resolved = _resolve_id_prefix(value, list(name_map), "分区")
    if resolved is not None:
        return resolved
    by_name = [pid for pid, name in name_map.items() if name == value]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise CliError(f"存在多个同名分区 {value!r}，请用 ID 指定")
    raise CliError(f"分区不存在: {value!r}（用 partitions 查看分区名称与 ID）")


def _resolve_ids(args, svc) -> list[str]:
    """Resolve positional ids + --match into a verified task-id list.

    Task ids may be full UUIDs or unique prefixes (>=8 chars).
    """
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
    all_ids = [t.id for t in svc.get_all()]
    verified: list[str] = []
    for value in ids:
        task_id = _resolve_id_prefix(value, all_ids, "任务")
        if task_id is None:
            raise CliError(f"任务不存在: {value}")
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
    f = _build_filter(args, svc)
    total = svc.count(f)
    tasks = svc.search(f)
    return {
        "type": "task_list",
        "count": len(tasks),
        "total": total,
        "tasks": _with_names(svc, tasks),
    }


def _cmd_activity(args, svc, config) -> dict:
    """Activity timeline for one day (default today)."""
    target = _parse_date(args.date) if args.date else date.today()
    pid = _resolve_partition_id(svc, args.partition) if args.partition else None
    tags = set(args.tag) if getattr(args, "tag", None) else None
    name_map = svc.get_partition_name_map()
    entries: list[dict] = []
    created = done = 0
    for t in svc.get_all():
        if pid and t.partition_id != pid:
            continue
        if tags and not tags.issubset(set(t.tags)):
            continue
        for e in t.activity_log or []:
            ts = str(e.get("ts", ""))
            if ts[:10] != target.isoformat():
                continue
            content = str(e.get("content", ""))
            if content == "创建任务":
                created += 1
            if e.get("status") == "DONE":
                done += 1
            entries.append({
                "ts": ts,
                "task_id": t.id,
                "task_title": t.title,
                "content": content,
                "status": e.get("status", ""),
                "progress": e.get("progress", 0),
                "partition_name": name_map.get(t.partition_id or "", ""),
            })
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return {
        "type": "activity",
        "date": target.isoformat(),
        "entry_count": len(entries),
        "task_count": len({e["task_id"] for e in entries}),
        "created": created,
        "done": done,
        "entries": entries,
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

    partition_id = _resolve_partition_id(svc, args.partition) if args.partition else svc.ensure_default_partition()
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
        task.partition_id = _resolve_partition_id(svc, args.partition)
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


def _cmd_log(args, svc, config) -> dict:
    """Append one activity-log entry — mirrors the GUI's 追加进展."""
    ids = _resolve_ids(args, svc)
    if len(ids) > 1:
        raise CliError("log 一次只能追加到一个任务")
    task = svc.get_task(ids[0])
    entry_status = TaskStatus.from_string(args.status) if args.status else task.status
    if args.status and args.status.upper() not in _STATUS_VALUES:
        raise CliError(f"无效状态: {args.status!r}")
    progress = args.progress if args.progress is not None else task.progress
    entry = {
        "ts": datetime.now().isoformat(),
        "content": args.content,
        "status": entry_status.value,
        "progress": progress,
    }
    if args.dry_run:
        return {"type": "dry_run", "command": "log",
                "changes": [f"追加活动记录: {args.content}（{entry_status.value} {progress}%）"]}
    task.activity_log = list(task.activity_log or []) + [entry]
    if args.progress is not None:
        task.progress = args.progress
    task = svc.update_task(task)
    if entry_status == TaskStatus.DONE and task.status != TaskStatus.DONE:
        task = svc.change_task_status(task, TaskStatus.DONE)
    return {
        "type": "activity_entry", "task_id": task.id, "task_title": task.title,
        "ts": entry["ts"], "content": entry["content"],
        "status": entry["status"], "progress": entry["progress"],
    }


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
    pid = _resolve_partition_id(svc, args.partition) if args.partition else None
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
        pid = _resolve_partition_id(svc, pid)
        p = svc.upsert_partition(name, partition_id=pid)
        return {"type": "partition", "partition": _partition_dict(p, svc)}
    if args.rm:
        pid = _resolve_partition_id(svc, args.rm)
        svc.delete_partition(pid)
        return {"type": "partition_deleted", "id": pid}
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


def _cmd_report(args, svc, config) -> dict:
    """Weekly/monthly report summary — single-partition, tag-grouped.

    Mirrors the GUI 活动分析 export semantics: one partition at a time,
    ``#xx`` sections are task tags, all activity tags exported by default.
    """
    today = date.today()
    period = args.period or "week"
    if args.date_from:
        d_from = _parse_date(args.date_from)
    elif period == "month":
        shifted = today.month + (args.offset or 0)
        year, month = today.year + (shifted - 1) // 12, (shifted - 1) % 12 + 1
        d_from = date(year, month, 1)
    else:
        monday = today - timedelta(days=today.isoweekday() - 1)
        d_from = monday + timedelta(weeks=(args.offset or 0))
    d_to = _parse_date(args.date_to) if args.date_to else today

    # 分区优先：未指定时取默认分区（与活动分析按单一分区触发一致）
    if args.partition:
        pid = _resolve_partition_id(svc, args.partition)
    else:
        pid = svc.ensure_default_partition()
    name_map = svc.get_partition_name_map()
    tags_filter = set(args.tag) if getattr(args, "tag", None) else None
    from_iso, to_iso = d_from.isoformat(), d_to.isoformat()

    groups: dict[str, dict[str, list]] = {}
    stats = {"entries": 0, "touched_tasks": 0, "completed": 0, "created": 0}

    def _bucket(task: Task, key: str, item: dict) -> None:
        """每个任务只归入其主标签组（第一个标签），避免多标签重复出现."""
        tag = task.tags[0] if task.tags else "未分类"
        groups.setdefault(tag, {"worked": [], "planned": []})[key].append(item)

    def _noise(content: str) -> bool:
        return (
            content == "创建任务"
            or content.startswith("[批量操作]")
            or content.startswith("状态变更为")
        )

    def _to_date(value) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    for t in svc.get_all():
        if t.partition_id != pid:
            continue
        if tags_filter and not tags_filter.issubset(set(t.tags)):
            continue
        logs = sorted(t.activity_log or [], key=lambda e: str(e.get("ts", "")))
        in_range = [e for e in logs
                    if from_iso <= str(e.get("ts", ""))[:10] <= to_iso]
        created_in = bool(t.created_at) and from_iso <= str(t.created_at)[:10] <= to_iso
        completed_at = _to_date(t.completed_at)
        completed_in = bool(completed_at) and d_from <= completed_at <= d_to
        # 「本周工作内容」= 期内完成 / 期内有实质进展 / 期内创建（创建本身即本周工作）
        substantive = [
            e for e in in_range
            if str(e.get("content", "")).strip() and not _noise(str(e.get("content", "")).strip())
        ]
        active = not t.archived and not t.suspended and t.status != TaskStatus.DONE
        # 仅创建、未补进展 → 标注无进展，且进入下周计划优先排列
        no_progress = created_in and not substantive and not completed_in
        if substantive or completed_in or created_in:
            stats["touched_tasks"] += 1
            stats["entries"] += len(in_range)
            stats["created"] += 1 if created_in else 0
            stats["completed"] += 1 if completed_in else 0
            points = [str(e.get("content", "")).strip() for e in substantive]
            progress_from = in_range[0].get("progress") if in_range else None
            progress_to = in_range[-1].get("progress") if in_range else None
            _bucket(t, "worked", {
                "task_id": t.id,
                "title": t.title,
                "status": t.status.value,
                "completed_in_period": completed_in,
                "no_progress": no_progress,
                "points": points,
                "progress_from": progress_from,
                "progress_to": progress_to,
            })
        if active and (no_progress or not (substantive or completed_in)):
            _bucket(t, "planned", {
                "task_id": t.id,
                "title": t.title,
                "status": t.status.value,
                "deadline_date": t.deadline_date.isoformat() if t.deadline_date else None,
                "urgency": t.urgency,
                "countdown_days": (t.deadline_date - today).days if t.deadline_date else None,
                "created_in_period": created_in,
            })

    for g in groups.values():
        g["worked"].sort(key=lambda i: i["task_id"])
        # 期内创建无进展的任务优先安排（置顶），其余按截止日/优先级
        g["planned"].sort(
            key=lambda i: (
                0 if i.get("created_in_period") else 1,
                i.get("deadline_date") or "9999",
                i["urgency"],
            )
        )
    return {
        "type": "report",
        "period": period,
        "partition_id": pid,
        "partition_name": name_map.get(pid, ""),
        "from": from_iso,
        "to": to_iso,
        "stats": stats,
        "groups": [{"tag": tag, **g} for tag, g in sorted(groups.items())],
    }


def _cmd_export(args, svc, config) -> dict:
    pid = _resolve_partition_id(svc, args.partition) if args.partition else None
    f = TaskFilter(partition_id=pid, show_archived=True)
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
    "activity": _cmd_activity,
    "add": _cmd_add,
    "edit": _cmd_edit,
    "done": _cmd_done,
    "log": _cmd_log,
    "rm": _cmd_rm,
    "tags": _cmd_tags,
    "partitions": _cmd_partitions,
    "archive": _cmd_archive,
    "recurrence": _cmd_recurrence,
    "reminder": _cmd_reminder,
    "export": _cmd_export,
    "report": _cmd_report,
}

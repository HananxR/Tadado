"""Stable JSON output schema + human-readable rendering for CLI results."""

from __future__ import annotations

import json
from datetime import date, datetime

from ..models.task import Task


def task_to_dict(task: Task, partition_name: str = "") -> dict:
    """Serialize a Task into the stable CLI JSON schema."""
    completed = task.completed_at
    if isinstance(completed, (date, datetime)):
        completed = completed.isoformat()
    return {
        "id": task.id,
        "title": task.title,
        "raw_md": task.raw_md,
        "status": task.status.value,
        "status_display": task.status.display_name,
        "tags": task.tags,
        "urgency": task.urgency,
        "progress": task.progress,
        "archived": task.archived,
        "suspended": task.suspended,
        "scheduled_date": task.scheduled_date.isoformat() if task.scheduled_date else None,
        "deadline_date": task.deadline_date.isoformat() if task.deadline_date else None,
        "deadline_time": task.deadline_time,
        "partition_id": task.partition_id or "",
        "partition_name": partition_name,
        "recurrence_rule": task.recurrence_rule,
        "notes": task.notes,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": completed,
        "is_overdue": task.is_overdue,
    }


def render(result: dict, fmt: str = "json") -> str:
    """Render a command result as JSON (default) or human-readable text."""
    if fmt == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)
    return _render_human(result)


# ------------------------------------------------------------------
# Human rendering
# ------------------------------------------------------------------

def _render_human(result: dict) -> str:
    rtype = result.get("type")
    if rtype == "task_list":
        lines = [f"任务列表（{result['count']} / 共 {result['total']}）:"]
        lines.extend(_task_lines(result["tasks"]))
        return "\n".join(lines)
    if rtype == "today":
        lines = [f"今日摘要（{result['date']}，近 {result['days']} 天）:"]
        for group, label in (("overdue", "逾期"), ("due_today", "今日到期"),
                             ("due_soon", "临近"), ("doing", "进行中")):
            tasks = result.get(group) or []
            lines.append(f"\n【{label}】{len(tasks)}")
            lines.extend(_task_lines(tasks))
        return "\n".join(lines)
    if rtype == "task":
        lines = ["任务:", _task_lines([result["task"]])[0]]
        return "\n".join(lines)
    if rtype == "status_change":
        return f"状态已变更: {result['count']} 个任务 → {result['status']}"
    if rtype == "deleted":
        return f"已删除: {result['count']} 个任务"
    if rtype == "archived":
        return f"已归档: {result['count']} 个任务"
    if rtype == "dry_run":
        lines = [f"[dry-run] {result.get('command')} 将执行以下变更:"]
        for change in result.get("changes", []):
            if isinstance(change, dict) and "title" in change:
                lines.append(f"  - {change['title']}: {change.get('from', '')} → {change.get('to', '')}")
            elif isinstance(change, str):
                lines.append(f"  {change}")
        before, after = result.get("before"), result.get("after")
        if before is not None and after is not None:
            lines.append(f"  修改前: {before}")
            lines.append(f"  修改后: {after}")
        return "\n".join(lines)
    if rtype == "tags":
        entries = result["tags"]
        if entries and isinstance(entries[0], dict):
            return "标签:\n" + "\n".join(f"  #{e['tag']} ({e['count']})" for e in entries)
        return "标签:\n" + "\n".join(f"  #{t}" for t in entries)
    if rtype == "partition_list":
        lines = ["分区:"]
        for p in result["partitions"]:
            pw = " [加密]" if p.get("has_password") else ""
            lines.append(f"  {p['id'][:8]} {p['name']} ({p['task_count']} 任务){pw}")
        return "\n".join(lines)
    if rtype == "partition":
        p = result["partition"]
        return f"分区已保存: {p['name']} ({p['id'][:8]})"
    if rtype == "partition_deleted":
        return f"分区已删除: {result['id'][:8]}"
    if rtype == "reminder":
        r = result
        return (
            f"提醒: {'开启' if r['enabled'] else '关闭'}\n"
            f"  每日摘要: {r['daily_digest_time']}\n"
            f"  安静时段: {r['quiet_hours_start']} - {r['quiet_hours_end']}"
        )
    if rtype == "recurrence":
        rule = result.get("rule")
        return f"周期任务 {result['task_id'][:8]}: {rule or '（无周期规则）'}"
    if rtype == "export":
        return f"已导出 {result['count']} 个任务 → {result['path']}"
    return json.dumps(result, ensure_ascii=False, indent=2)


def _task_lines(tasks: list[dict]) -> list[str]:
    lines = []
    for t in tasks:
        when = t.get("deadline_date") or t.get("scheduled_date") or ""
        tags = " ".join(f"#{tag}" for tag in t.get("tags") or [])
        lines.append(
            f"  [{t['id'][:8]}] {t['status_display']:<4} {when:<12} {t['title']} {tags}".rstrip()
        )
    return lines

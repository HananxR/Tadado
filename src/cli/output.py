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
    if rtype == "activity_entry":
        e = result
        return (
            f"已追加活动记录: {e['task_title']} — {e['content']}"
            f"（{e['status']} {e['progress']}%）"
        )
    if rtype == "activity":
        lines = [
            f"活动记录（{result['date']}，共 {result['entry_count']} 条 / "
            f"{result['task_count']} 个任务，新增 {result['created']}，完成 {result['done']}）:"
        ]
        for e in result["entries"]:
            ts = e["ts"][11:19] if len(e["ts"]) >= 19 else e["ts"]
            lines.append(
                f"  {ts} [{e['task_id'][:8]}] {e['task_title']} — {e['content']}"
                f"（{e['status']} {e['progress']}%）「{e['partition_name']}」"
            )
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
    if rtype == "report":
        is_week = result.get("period") == "week"
        pname = result.get("partition_name") or ""
        title = f"{'周报' if is_week else '月报'}摘要（{pname}分区 · {result['from']} ~ {result['to']}）"
        cur = "本周" if is_week else "本月"
        nxt = "下周" if is_week else "下月"
        lines = [title, ""]
        for section, label in (("worked", f"{cur}工作内容"), ("planned", f"{nxt}工作计划")):
            lines.append(f"{label}：")
            lines.append("")
            for g in result["groups"]:
                items = g[section]
                if not items:
                    continue
                lines.append(f"#{g['tag']}")
                lines.append("")
                for i, item in enumerate(items, 1):
                    if section == "worked" and item["points"]:
                        suffix = "；".join(item["points"]) + "；"
                        lines.append(f"{i}. {item['title']}：{suffix}")
                    elif section == "worked" and item.get("no_progress"):
                        lines.append(f"{i}. {item['title']}；（无进展）")
                    else:
                        lines.append(f"{i}. {item['title']}；")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"
    if rtype == "export":
        return f"已导出 {result['count']} 个任务 → {result['path']}"
    return json.dumps(result, ensure_ascii=False, indent=2)


def _countdown(t: dict) -> str:
    """剩余天数倒计时：剩 N 天 / 今天到期 / 已逾期 N 天；无截止为空."""
    deadline = t.get("deadline_date")
    if not deadline:
        return ""
    delta = (date.fromisoformat(deadline) - date.today()).days
    if delta < 0:
        return f"已逾期 {-delta} 天"
    if delta == 0:
        return "今天到期"
    return f"剩 {delta} 天"


def _task_lines(tasks: list[dict]) -> list[str]:
    lines = []
    for t in tasks:
        when = t.get("deadline_date") or t.get("scheduled_date") or ""
        countdown = _countdown(t)
        tags = " ".join(f"#{tag}" for tag in t.get("tags") or [])
        partition = f"「{t['partition_name']}」" if t.get("partition_name") else ""
        lines.append(
            f"  [{t['id'][:8]}] {t['status_display']:<4} {when:<12} "
            f"({countdown}) {t['title']} {tags} {partition}".rstrip()
        )
    return lines

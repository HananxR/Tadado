"""Argument parser for the Tadado CLI."""

from __future__ import annotations

import argparse

_STATUS_CHOICES = ["TODO", "DOING", "DONE", "OVERDUE"]
_SORT_CHOICES = ["deadline", "urgency", "created", "title", "status", "scheduled"]


def build_parser() -> argparse.ArgumentParser:
    """Build the full CLI parser with one subparser per command."""
    p = argparse.ArgumentParser(
        prog="tadado-cli",
        description="Tadado 命令行接口 — 供 Claude Code skill 与终端使用",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="列出任务")
    p_list.add_argument("--partition", help="分区 ID")
    p_list.add_argument("--status", action="append", choices=_STATUS_CHOICES,
                        help="状态过滤（可多次）")
    p_list.add_argument("--tag", action="append", help="标签过滤（可多次）")
    p_list.add_argument("--keyword", help="标题/内容关键词")
    p_list.add_argument("--from", dest="date_from", help="截止日起 YYYY-MM-DD")
    p_list.add_argument("--to", dest="date_to", help="截止日止 YYYY-MM-DD")
    p_list.add_argument("--overdue", action="store_true", help="只看逾期")
    p_list.add_argument("--archived", action="store_true", help="包含已归档")
    p_list.add_argument("--urgency", type=int, choices=[0, 1, 2, 3],
                        help="优先级 0紧急/1重要/2关注/3普通")
    p_list.add_argument("--limit", type=int, default=50, help="返回条数（默认 50）")
    p_list.add_argument("--offset", type=int, default=0)
    p_list.add_argument("--sort", choices=_SORT_CHOICES, default="deadline")
    p_list.add_argument("--desc", action="store_true", help="降序")

    # today
    p_today = sub.add_parser("today", help="今日摘要（逾期/今日到期/临近/进行中）")
    p_today.add_argument("--days", type=int, default=2, help="临近窗口天数（默认 2）")

    # activity
    p_act = sub.add_parser("activity", help="指定日期的活动记录时间线")
    p_act.add_argument("--date", dest="date", help="日期 YYYY-MM-DD（默认今天）")
    p_act.add_argument("--partition", help="分区 ID/名称")
    p_act.add_argument("--tag", action="append", help="标签过滤（可多次）")

    # add
    p_add = sub.add_parser("add", help="新建任务（Markdown 行为主）")
    p_add.add_argument("markdown", nargs="?", help="Markdown 任务行，如 '- [*] TODO<2026-08-20> 买咖啡 #工作'")
    p_add.add_argument("--title", help="任务标题（无 Markdown 时使用）")
    p_add.add_argument("--partition", help="分区 ID")
    p_add.add_argument("--status", choices=_STATUS_CHOICES, help="状态（默认 TODO）")
    p_add.add_argument("--due", help="截止日 YYYY-MM-DD[ HH:MM]")
    p_add.add_argument("--scheduled", help="计划日 YYYY-MM-DD")
    p_add.add_argument("--tags", help="标签，逗号分隔（覆盖 Markdown 中的标签）")
    p_add.add_argument("--urgency", type=int, choices=[0, 1, 2, 3], help="优先级")
    p_add.add_argument("--notes", help="备注")
    p_add.add_argument("--recur", help="周期规则 +1d/+1w/+1m/+1y")

    # edit
    p_edit = sub.add_parser("edit", help="修改任务")
    p_edit.add_argument("ids", nargs="*", help="任务 ID")
    p_edit.add_argument("--match", help="按标题/内容关键词定位（唯一匹配才生效）")
    p_edit.add_argument("--title", help="新标题")
    p_edit.add_argument("--due", help="截止日 YYYY-MM-DD[ HH:MM]")
    p_edit.add_argument("--clear-due", action="store_true", help="清除截止日")
    p_edit.add_argument("--scheduled", help="计划日 YYYY-MM-DD")
    p_edit.add_argument("--clear-scheduled", action="store_true", help="清除计划日")
    p_edit.add_argument("--tags", help="标签，逗号分隔（整体替换）")
    p_edit.add_argument("--urgency", type=int, choices=[0, 1, 2, 3], help="优先级")
    p_edit.add_argument("--notes", help="备注")
    p_edit.add_argument("--recur", help="周期规则 +1d/+1w/+1m/+1y（空串清除）")
    p_edit.add_argument("--status", choices=_STATUS_CHOICES, help="状态")
    p_edit.add_argument("--partition", help="移动到分区 ID")
    p_edit.add_argument("--dry-run", action="store_true", help="只预览不执行")

    # log
    p_log = sub.add_parser("log", help="追加活动进展记录（对应 GUI 追加进展）")
    p_log.add_argument("ids", nargs="*", help="任务 ID")
    p_log.add_argument("--match", help="按关键词定位（唯一匹配才生效）")
    p_log.add_argument("--content", required=True, help="进展内容")
    p_log.add_argument("--status", choices=_STATUS_CHOICES,
                       help="状态（默认任务当前状态；选 DONE 同时完成任务）")
    p_log.add_argument("--progress", type=int, help="进度 0-100")
    p_log.add_argument("--dry-run", action="store_true", help="只预览不执行")

    # done
    p_done = sub.add_parser("done", help="变更任务状态（默认完成）")
    p_done.add_argument("ids", nargs="*", help="任务 ID")
    p_done.add_argument("--match", help="按关键词定位（唯一匹配才生效）")
    p_done.add_argument("--status", choices=_STATUS_CHOICES, help="目标状态（默认 DONE）")
    p_done.add_argument("--dry-run", action="store_true", help="只预览不执行")

    # rm
    p_rm = sub.add_parser("rm", help="删除任务")
    p_rm.add_argument("ids", nargs="*", help="任务 ID")
    p_rm.add_argument("--match", help="按关键词定位（唯一匹配才生效）")
    p_rm.add_argument("--dry-run", action="store_true", help="只预览不执行")

    # tags
    p_tags = sub.add_parser("tags", help="列出标签")
    p_tags.add_argument("--partition", help="分区 ID")
    p_tags.add_argument("--counts", action="store_true", help="含任务计数")

    # partitions
    p_parts = sub.add_parser("partitions", help="分区管理")
    p_parts.add_argument("--add", metavar="NAME", help="新建分区")
    p_parts.add_argument("--rename", nargs=2, metavar=("ID", "NAME"), help="重命名分区")
    p_parts.add_argument("--rm", metavar="ID", help="删除分区")

    # archive
    p_arch = sub.add_parser("archive", help="归档任务")
    p_arch.add_argument("ids", nargs="*", help="任务 ID")
    p_arch.add_argument("--match", help="按关键词定位（唯一匹配才生效）")
    p_arch.add_argument("--all", action="store_true", help="归档全部已完成任务")
    p_arch.add_argument("--dry-run", action="store_true", help="只预览不执行")

    # recurrence
    p_rec = sub.add_parser("recurrence", help="查看/设置周期规则")
    p_rec.add_argument("ids", nargs="*", help="任务 ID")
    p_rec.add_argument("--match", help="按关键词定位（唯一匹配才生效）")
    p_rec.add_argument("--rule", help="周期规则 +1d/+1w/+1m/+1y")

    # reminder
    p_rem = sub.add_parser("reminder", help="查看/设置提醒配置")
    p_rem.add_argument("--enable", action="store_true", help="开启提醒")
    p_rem.add_argument("--disable", action="store_true", help="关闭提醒")
    p_rem.add_argument("--digest-time", help="每日摘要时间 HH:MM")
    p_rem.add_argument("--quiet-start", help="安静时段开始 HH:MM")
    p_rem.add_argument("--quiet-end", help="安静时段结束 HH:MM")

    # export
    p_exp = sub.add_parser("export", help="导出任务")
    p_exp.add_argument("--fmt", choices=["md", "xlsx"], default="md", help="格式（默认 md）")
    p_exp.add_argument("--partition", help="分区 ID（默认全部分区）")
    p_exp.add_argument("--out", help="输出路径（默认 tadado_tasks.md/.xlsx）")

    return p

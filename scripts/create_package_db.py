"""
Generate the package database for frozen distribution.

Creates a fresh SQLite DB with 4 partitions (工作/学习/个人/演示空间)
and seeds ~15 demo tasks covering all core features into 演示空间.

Run ONLY during the build process (build.bat), never in development.
"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

# Ensure the project root is on sys.path so src imports work
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.repository import TaskRepository
from src.models.task import Task
from src.models.task_status import TaskStatus
from src.services.md_parser import MarkdownTaskParser

DB_PATH = _PROJECT_ROOT / "resources" / "desktodoseq.data"


def main() -> None:
    # Allow overriding output path via CLI argument (for testing)
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH

    # ------------------------------------------------------------------
    # Safety: refuse to run over an active dev database (only for default path)
    # ------------------------------------------------------------------
    if output_path == DB_PATH and output_path.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute(
                "SELECT COUNT(*) FROM partitions WHERE name = ?", ("测试分区",)
            ).fetchone()
            if row and row[0] > 0:
                print(
                    "ERROR: This looks like a dev database "
                    "(contains '测试分区'). Aborting."
                )
                conn.close()
                sys.exit(1)
            conn.close()
        except sqlite3.OperationalError:
            pass  # tables don't exist yet, safe
        output_path.unlink()
        print(f"Removed existing DB: {output_path}")

    # ------------------------------------------------------------------
    # Phase 1: Create DB and run all migrations
    # ------------------------------------------------------------------
    repo = TaskRepository(str(output_path))
    repo.open()  # creates tables, FTS indexes, default partitions (工作/个人/学习)

    # ------------------------------------------------------------------
    # Phase 2: Delete migration-created default partitions
    # ------------------------------------------------------------------
    for p in repo.get_all_partitions():
        repo.delete_partition(p["id"])
    print("Deleted default partitions from migration.")

    # ------------------------------------------------------------------
    # Phase 3: Create the 4 package partitions (sort_order 0..3)
    # ------------------------------------------------------------------
    pid_work = repo.upsert_partition("工作", sort_order=0)["id"]
    pid_study = repo.upsert_partition("学习", sort_order=1)["id"]
    pid_personal = repo.upsert_partition("个人", sort_order=2)["id"]
    pid_demo = repo.upsert_partition("演示空间", sort_order=3)["id"]
    print(
        f"Created partitions: 工作={pid_work[:8]}... "
        f"学习={pid_study[:8]}... "
        f"个人={pid_personal[:8]}... "
        f"演示空间={pid_demo[:8]}..."
    )

    # ------------------------------------------------------------------
    # Phase 4: Seed ~15 demo tasks into 演示空间
    # ------------------------------------------------------------------
    parser = MarkdownTaskParser()
    today = date.today()

    def _ago(days: int = 0, hours: int = 0) -> str:
        return (datetime.now() - timedelta(days=days, hours=hours)).isoformat()

    # Each entry: (raw_md, title, status, urgency, tags, activity_log, progress, completed_at, recurrence_rule, suspended, notes)
    # - raw_md: valid Markdown line parsable by MarkdownTaskParser
    # - activity_log: list of {"ts": iso, "content": str, "status": str} dicts
    # - completed_at: datetime for DONE tasks
    demos: list[tuple] = [
        # ── 1. DONE — complete status cycle, rich activity log ──
        (
            f"- [x] <{today - timedelta(days=2)}> 完成Q3产品需求文档评审 #工作 #产品",
            "完成Q3产品需求文档评审",
            TaskStatus.DONE,
            0,  # urgency 0 = 紧急
            ["工作", "产品"],
            [
                {"ts": _ago(4), "content": "收集各团队Q3数据报表，整理需求池", "status": "TODO"},
                {"ts": _ago(3), "content": "确定PRD框架：功能概述、用户故事、验收标准", "status": "DOING", "progress": 30},
                {"ts": _ago(2), "content": "完成初稿 15 页，交付组长审阅", "status": "DOING", "progress": 70},
                {"ts": _ago(1), "content": "终稿审核通过 ✓，同步到Confluence", "status": "DONE", "progress": 100},
            ],
            100,
            datetime.now() - timedelta(days=2),  # completed_at
            None,  # no recurrence
            False,  # not suspended
            None,  # no notes
        ),
        # ── 2. DOING — urgency 0, multi-tag, activity log ──
        (
            f"- [***] <{today + timedelta(days=2)}> 修复用户登录模块并发Bug #工作 #后端 #Bug",
            "修复用户登录模块并发Bug",
            TaskStatus.DOING,
            0,
            ["工作", "后端", "Bug"],
            [
                {"ts": _ago(3), "content": "定位问题：高并发下 session 锁竞争导致死锁", "status": "TODO"},
                {"ts": _ago(1), "content": "引入 Redis 分布式锁，重构 token 刷新逻辑，已完成 60%", "status": "DOING", "progress": 60},
                {"ts": datetime.now().isoformat(), "content": "单元测试通过，等待 Code Review", "status": "DOING", "progress": 80},
            ],
            80,
            None,
            None,
            False,
            None,
        ),
        # ── 3. TODO — urgency 1, near-term deadline ──
        (
            f"- [** ] <{today + timedelta(days=5)}> 准备周五组会演示文稿 #工作 #团队",
            "准备周五组会演示文稿",
            TaskStatus.TODO,
            1,
            ["工作", "团队"],
            [
                {"ts": datetime.now().isoformat(), "content": "确定汇报主题：Sprint 回顾与下周期规划", "status": "TODO"},
            ],
            0,
            None,
            None,
            False,
            None,
        ),
        # ── 4. TODO — recurrence +1w, health tag ──
        (
            f"- [   ] <{today + timedelta(days=5)}> 每周三次有氧运动 #健康 #运动",
            "每周三次有氧运动",
            TaskStatus.TODO,
            3,
            ["健康", "运动"],
            [
                {"ts": _ago(2), "content": "本周完成 1/3 次：跑步 5km，平均配速 5'30\"", "status": "TODO"},
            ],
            0,
            None,
            "+1w",  # recurrence rule
            False,
            None,
        ),
        # ── 5. OVERDUE — auto overdue detection demo ──
        (
            f"- [*  ] <{today - timedelta(days=3)}> 归还借阅的书籍 #生活 #日常",
            "归还借阅的书籍",
            TaskStatus.OVERDUE,
            2,
            ["生活", "日常"],
            [
                {"ts": _ago(10), "content": "从市图书馆借阅《系统设计》和《代码整洁之道》", "status": "TODO"},
            ],
            0,
            None,
            None,
            False,
            None,
        ),
        # ── 6. DOING — urgency 1, rich activity log with progress ──
        (
            f"- [** ] <{today + timedelta(days=10)}> 学习Kubernetes基础 #学习 #技术",
            "学习Kubernetes基础",
            TaskStatus.DOING,
            1,
            ["学习", "技术"],
            [
                {"ts": _ago(7), "content": "完成环境搭建：minikube + kubectl + 本地集群", "status": "DOING", "progress": 10},
                {"ts": _ago(4), "content": "学习 Pod、Deployment、Service 核心概念，做笔记 5 页", "status": "DOING", "progress": 30},
                {"ts": _ago(1), "content": "动手实践：部署一个 3 副本的 Nginx + 负载均衡，遇到 Ingress 配置问题", "status": "DOING", "progress": 50},
            ],
            50,
            None,
            None,
            False,
            None,
        ),
        # ── 7. TODO — urgency 2, deadline only ──
        (
            f"- [*  ] <{today + timedelta(days=3)}> 预约牙科洗牙 #健康 #生活",
            "预约牙科洗牙",
            TaskStatus.TODO,
            2,
            ["健康", "生活"],
            [],
            0,
            None,
            None,
            False,
            None,
        ),
        # ── 8. OVERDUE — urgency 0, past deadline ──
        (
            f"- [***] <{today - timedelta(days=1)}> 整理本月房租账单 #生活 #财务",
            "整理本月房租账单",
            TaskStatus.OVERDUE,
            0,
            ["生活", "财务"],
            [
                {"ts": _ago(5), "content": "导出支付宝账单 CSV（1-15日）", "status": "TODO"},
                {"ts": _ago(3), "content": "导出微信账单 CSV，发现几笔不明扣款需核实", "status": "TODO"},
            ],
            0,
            None,
            None,
            False,
            None,
        ),
        # ── 9. DOING — urgency 2, writing task with progress ──
        (
            f"- [*  ] <{today + timedelta(days=7)}> 编写技术博客：Python装饰器详解 #学习 #写作",
            "编写技术博客：Python装饰器详解",
            TaskStatus.DOING,
            2,
            ["学习", "写作"],
            [
                {"ts": _ago(5), "content": "确定选题和三级大纲：基础装饰器 → 带参数装饰器 → 类装饰器 → 实战案例", "status": "TODO"},
                {"ts": _ago(3), "content": "完成第一章草稿：函数是一等公民、闭包原理", "status": "DOING", "progress": 40},
                {"ts": _ago(1), "content": "编写代码示例：计时器、日志、权限校验三个装饰器", "status": "DOING", "progress": 60},
            ],
            60,
            None,
            None,
            False,
            None,
        ),
        # ── 10. TODO — urgency 1, upcoming deadline ──
        (
            f"- [** ] <{today + timedelta(days=4)}> 给朋友寄生日礼物 #生活 #社交",
            "给朋友寄生日礼物",
            TaskStatus.TODO,
            1,
            ["生活", "社交"],
            [
                {"ts": _ago(2), "content": "选定礼物：机械键盘（Cherry MX 红轴），朋友念叨半年了", "status": "TODO"},
            ],
            0,
            None,
            None,
            False,
            None,
        ),
        # ── 11. TODO — suspended, far future ──
        (
            f"- [   ] <{today + timedelta(days=30)}> 研究周末短途旅行攻略 #生活 #旅行",
            "研究周末短途旅行攻略",
            TaskStatus.TODO,
            3,
            ["生活", "旅行"],
            [
                {"ts": _ago(10), "content": "初步筛选：杭州（西湖徒步）、苏州（园林+美食）、莫干山（民宿+徒步）", "status": "TODO"},
            ],
            0,
            None,
            None,
            True,  # suspended
            None,
        ),
        # ── 12. TODO — no deadline, urgency 3 ──
        (
            f"- [   ]  更新API文档 #工作 #文档",
            "更新API文档",
            TaskStatus.TODO,
            3,
            ["工作", "文档"],
            [],
            0,
            None,
            None,
            False,
            None,
        ),
        # ── 13. DONE — completed with activity log ──
        (
            f"- [x] <{today - timedelta(days=1)}> 超市采购食材 #生活 #购物",
            "超市采购食材",
            TaskStatus.DONE,
            2,
            ["生活", "购物"],
            [
                {"ts": _ago(2), "content": "列购物清单：蔬菜、水果、牛奶、鸡蛋、鸡胸肉", "status": "TODO"},
                {"ts": _ago(1), "content": "完成采购，花费 ¥186.5，比预算省了 ¥13.5 😊", "status": "DONE", "progress": 100},
            ],
            100,
            datetime.now() - timedelta(days=1),
            None,
            False,
            None,
        ),
        # ── 14. DOING — urgency 1, reading task ──
        (
            f"- [** ] <{today + timedelta(days=5)}> 读《重构》第8章 #学习 #阅读",
            "读《重构》第8章",
            TaskStatus.DOING,
            1,
            ["学习", "阅读"],
            [
                {"ts": _ago(3), "content": "开始第 8 章：简化条件表达式，已读 15 页", "status": "DOING", "progress": 30},
                {"ts": _ago(1), "content": "完成：分解条件表达式、合并条件表达式、以卫语句取代嵌套", "status": "DOING", "progress": 65},
            ],
            65,
            None,
            None,
            False,
            "第 8 章重点：Replace Nested Conditional with Guard Clauses 这个重构手法在日常 CR 中非常实用，建议结合项目代码实践。",
        ),
        # ── 15. TODO — far future, urgency 3 ──
        (
            f"- [   ] <{today + timedelta(days=21)}> 提交年假申请 #工作 #行政",
            "提交年假申请",
            TaskStatus.TODO,
            3,
            ["工作", "行政"],
            [],
            0,
            None,
            None,
            False,
            None,
        ),
    ]

    count = 0
    for raw_md, title, status, urgency, tags, activity_log, progress, completed_at, recurrence_rule, suspended, notes in demos:
        parsed = parser.parse(raw_md)
        task = Task(
            id=str(uuid.uuid4()),
            raw_md=raw_md,
            title=title,
            status=status,
            urgency=urgency,
            tags=tags,
            deadline_date=parsed.deadline_date,
            deadline_time=parsed.deadline_time,
            scheduled_date=parsed.scheduled_date,
            partition_id=pid_demo,
            activity_log=activity_log,
            progress=progress,
            completed_at=completed_at,
            recurrence_rule=recurrence_rule,
            suspended=suspended,
            notes=notes,
        )
        repo.insert(task)
        count += 1

    repo.close()
    print(f"Seeded {count} demo tasks into 演示空间.")
    print(f"Package database created at: {output_path}")


if __name__ == "__main__":
    main()

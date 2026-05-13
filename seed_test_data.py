"""Populate the database with realistic daily-life tasks for UX testing."""

from src.models.repository import TaskRepository
from src.services.md_parser import MarkdownTaskParser
from src.models.task import Task
from src.config import AppConfig
import uuid
from datetime import datetime

config = AppConfig()
repo = TaskRepository(config.db_path())
repo.open()

parser = MarkdownTaskParser()

tasks_md = [
    # Work tasks
    "- [ ] TODO [#A] <2026-05-12> 完成Q2绩效评估报告 #work #urgent",
    "- [x] DOING [#B] <2026-05-11> 重构用户认证模块单元测试 #work #backend",
    "- [ ] TODO [#B] <2026-05-15> 准备周五技术分享PPT：Python异步编程 #work #study",
    "- [ ] WAIT [#C] <2026-05-20> 等待运维开通生产环境数据库权限 #work #blocked",
    "- [x] DONE [#B] <2026-05-10> 修复API分页查询total计数错误 #work #bug",
    "- [ ] TODO [#C] <2026-05-18> 更新项目README和API文档 #work #docs",

    # Health & Life
    "- [ ] URGENT [#A] <2026-05-12> 预约牙科复查，智齿发炎一周了 #health #urgent",
    "- [x] TODO [#B] <2026-05-11> 晨跑30分钟 #health #daily",
    "- [ ] TODO [#C] <2026-05-14> 整理衣柜，换季收纳冬装 #life #chore",
    "- [x] DONE [#B] <2026-05-09> 去超市采购一周食材 #life #weekly",
    "- [ ] DOING [#B] <2026-05-11> 给爸妈打电话问候 #life #family",

    # Study & Learning
    "- [ ] TODO [#B] <2026-05-13> 读完《系统设计面试》第5章 #study #reading",
    "- [ ] TODO [#A] <2026-05-16> 完成LeetCode周赛300题打卡 #study #coding",
    "- [x] DOING [#C] <2026-05-10> 学习Rust所有权与生命周期概念 #study #rust",
    "- [ ] LATER [#C] <2026-05-25> 报名AWS SAA认证考试 #study #cert",

    # Side project
    "- [ ] TODO [#B] <2026-05-17> DeskTodoSeq: 添加Markdown语法高亮功能 #dev #feature",
    "- [ ] TODO [#C] <2026-05-19> DeskTodoSeq: 设计应用图标和品牌配色 #dev #design",
    "- [x] DOING [#A] <2026-05-11> DeskTodoSeq: 优化UX体验，升级UI设计 #dev #current",
    "- [ ] TODO [#C] <2026-05-22> 写技术博客：如何用Python构建桌面应用 #writing #blog",

    # Financial
    "- [ ] TODO [#B] <2026-05-15> 整理本月开支，更新预算表 #finance #monthly",
    "- [ ] TODO [#C] <2026-05-20> 研究基金定投策略，调整投资组合 #finance #invest",
]

imported = 0
for md_text in tasks_md:
    try:
        parsed = parser.parse(md_text)
    except ValueError as e:
        print(f"  SKIP: {md_text[:50]}... reason: {e}")
        continue
    task = Task(
        id=str(uuid.uuid4()),
        raw_md=md_text,
        title=parsed.clean_title,
        status=parsed.status,
        priority=parsed.priority,
        tags=parsed.tags,
        scheduled_date=parsed.scheduled_date,
        deadline_date=parsed.deadline_date,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    repo.insert(task)
    imported += 1

print(f"Seeded {imported} tasks into the database.")
repo.close()

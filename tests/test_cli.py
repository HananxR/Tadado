"""CLI 层测试 — parser、命令执行、管道协议、e2e."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer

from src.cli.commands import CliError, execute
from src.cli.forward import try_forward
from src.cli.headless import _extract_format
from src.cli.output import render
from src.cli.parser import build_parser
from src.cli.protocol import PROTO_HEADER
from src.config import AppConfig
from src.services.task_service import TaskService


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    """One QCoreApplication for the module (protocol tests need it)."""
    app = QCoreApplication.instance() or QCoreApplication(["pytest"])
    return app


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return build_parser()


@pytest.fixture
def test_bus():
    """Per-test signal bus — isolates handlers from closed repositories."""
    from src.utils.signal_bus import SignalBus

    return SignalBus()


@pytest.fixture
def service(repository, test_bus) -> TaskService:
    return TaskService(repository, signal_bus=test_bus)


def _args(parser, *argv: str) -> argparse.Namespace:
    return parser.parse_args(list(argv))


# ------------------------------------------------------------------
# parser / headless helpers
# ------------------------------------------------------------------

def test_parser_all_commands(parser):
    """Each command parses with minimal args."""
    _args(parser, "list")
    _args(parser, "today")
    _args(parser, "add", "买咖啡")
    _args(parser, "edit", "--match", "咖啡", "--title", "x")
    _args(parser, "done", "abc")
    _args(parser, "rm", "--match", "x")
    _args(parser, "tags")
    _args(parser, "partitions")
    _args(parser, "archive", "--all")
    _args(parser, "recurrence", "--match", "x")
    _args(parser, "reminder")
    _args(parser, "export", "--fmt", "xlsx", "--out", "a.xlsx")


def test_extract_format_anywhere():
    argv, fmt = _extract_format(["--format", "human", "list", "--status", "TODO"])
    assert fmt == "human" and argv == ["list", "--status", "TODO"]
    argv, fmt = _extract_format(["list", "--format=human"])
    assert fmt == "human" and argv == ["list"]
    argv, fmt = _extract_format(["list"])
    assert fmt == "json" and argv == ["list"]


# ------------------------------------------------------------------
# list / today
# ------------------------------------------------------------------

def test_list_round_trip_and_count(parser, service):
    """list 返回 JSON schema，关键词搜索的 total 与 count 一致（count() 回归）."""
    a = _args(parser, "add", "- [*] TODO <2026-08-20> 买咖啡 #工作")
    execute("add", a, service)
    r = execute("list", _args(parser, "list", "--keyword", "咖啡"), service)
    assert r["total"] == 1 and r["count"] == 1
    t = r["tasks"][0]
    assert t["title"] == "买咖啡" and t["status"] == "TODO"
    assert t["urgency"] == 2 and t["tags"] == ["工作"]
    assert t["deadline_date"] == "2026-08-20"


def test_list_filters(parser, service, repository):
    # archive_days=0 会让 DONE 立即归档，先模拟正常配置
    repository.update_partition_archive_days(service.ensure_default_partition(), 30)
    execute("add", _args(parser, "add", "- [ ] TODO <2026-08-20> 任务A #工作"), service)
    execute("add", _args(parser, "add", "- [x] DONE <2026-08-15> 任务B #学习"), service)
    r = execute("list", _args(parser, "list", "--status", "DONE"), service)
    assert r["count"] == 1 and r["tasks"][0]["title"] == "任务B"
    r = execute("list", _args(parser, "list", "--tag", "学习"), service)
    assert r["count"] == 1
    r = execute("list", _args(parser, "list"), service)
    assert r["count"] == 2


def test_today_groups(parser, service):
    today = date.today()
    execute("add", _args(parser, "add", f"- [ ] TODO <{today - timedelta(days=1)}> 已逾期"), service)
    execute("add", _args(parser, "add", f"- [ ] TODO <{today}> 今日到期"), service)
    execute("add", _args(parser, "add", f"- [ ] TODO <{today + timedelta(days=1)}> 临近"), service)
    execute("add", _args(parser, "add", "- [ ] DOING 进行中无截止"), service)
    r = execute("today", _args(parser, "today"), service)
    assert [t["title"] for t in r["overdue"]] == ["已逾期"]
    assert [t["title"] for t in r["due_today"]] == ["今日到期"]
    assert [t["title"] for t in r["due_soon"]] == ["临近"]
    assert [t["title"] for t in r["doing"]] == ["进行中无截止"]


# ------------------------------------------------------------------
# add
# ------------------------------------------------------------------

def test_add_normalizes_missing_space(parser, service):
    """TODO<date> 无空格形式也能正确解析（LLM 常见写法）."""
    r = execute("add", _args(parser, "add", "- [ ] TODO<2026-08-20> 无空格日期"), service)
    assert r["task"]["title"] == "无空格日期"
    assert r["task"]["deadline_date"] == "2026-08-20"


def test_add_flags_only(parser, service):
    r = execute("add", _args(
        parser, "add", "--title", "纯flags任务", "--due", "2026-08-22 09:30",
        "--tags", "工作,生活", "--urgency", "0", "--notes", "备注内容", "--recur", "+1d",
    ), service)
    t = r["task"]
    assert t["title"] == "纯flags任务"
    assert t["deadline_date"] == "2026-08-22" and t["deadline_time"] == "09:30"
    assert t["tags"] == ["工作", "生活"] and t["urgency"] == 0
    assert t["notes"] == "备注内容" and t["recurrence_rule"] == "+1d"


def test_add_missing_title_errors(parser, service):
    with pytest.raises(CliError):
        execute("add", _args(parser, "add", "--due", "2026-08-22"), service)


# ------------------------------------------------------------------
# edit / done / rm / archive
# ------------------------------------------------------------------

def test_edit_and_dry_run(parser, service):
    execute("add", _args(parser, "add", "- [ ] TODO <2026-08-20> 编辑我"), service)
    dry = execute("edit", _args(parser, "edit", "--match", "编辑我", "--due", "2026-08-25", "--dry-run"), service)
    assert dry["type"] == "dry_run" and "2026-08-25" in dry["after"]
    r = execute("edit", _args(parser, "edit", "--match", "编辑我", "--due", "2026-08-25", "--urgency", "1"), service)
    assert r["task"]["deadline_date"] == "2026-08-25" and r["task"]["urgency"] == 1


def test_edit_ambiguous_match_errors(parser, service):
    execute("add", _args(parser, "add", "报告A"), service)
    execute("add", _args(parser, "add", "报告B"), service)
    with pytest.raises(CliError, match="匹配到多个任务"):
        execute("edit", _args(parser, "edit", "--match", "报告", "--title", "x"), service)


def test_id_prefix_resolution(parser, service):
    """>=8 位唯一 ID 前缀可解析为完整 ID（任务与分区同理）."""
    r = execute("add", _args(parser, "add", "前缀解析任务"), service)
    prefix = r["task"]["id"][:8]
    edited = execute("edit", _args(parser, "edit", prefix, "--title", "改过标题"), service)
    assert edited["task"]["title"] == "改过标题"

    p = execute("partitions", _args(parser, "partitions"), service)["partitions"][0]
    added = execute("add", _args(
        parser, "add", "- [ ] TODO <2026-08-20> 前缀分区任务", "--partition", p["id"][:8],
    ), service)
    assert added["task"]["partition_id"] == p["id"]
    listing = execute("list", _args(parser, "list", "--partition", p["id"][:8]), service)
    assert listing["count"] >= 1


def test_id_prefix_too_short_or_unknown(parser, service):
    with pytest.raises(CliError, match="任务不存在"):
        execute("edit", _args(parser, "edit", "abc", "--title", "x"), service)
    with pytest.raises(CliError, match="分区不存在"):
        execute("partitions", _args(parser, "partitions", "--rm", "0"), service)


def test_partition_by_name(parser, service):
    """--partition 支持分区名称（ID / 前缀 / 名称三通道）."""
    p = execute("partitions", _args(parser, "partitions"), service)["partitions"][0]
    name = p["name"]
    r = execute("add", _args(
        parser, "add", "- [ ] TODO <2026-08-20> 按名分区任务", "--partition", name,
    ), service)
    assert r["task"]["partition_id"] == p["id"]
    assert r["task"]["partition_name"] == name


def test_done_and_recurrence_clone(parser, service, repository, test_bus):
    from src.services.recurrence import TaskRecurrence

    repository.update_partition_archive_days(service.ensure_default_partition(), 30)
    recurrence = TaskRecurrence(repository, signal_bus=test_bus)  # mirrors app.py wiring
    execute("add", _args(
        parser, "add", "- [ ] TODO <2026-08-20> 周期任务", "--recur", "+1w",
    ), service)
    r = execute("done", _args(parser, "done", "--match", "周期任务"), service)
    assert r["count"] == 1 and r["status"] == "DONE"
    clones = [t for t in service.get_all() if t.title == "周期任务" and t.status.value == "TODO"]
    assert len(clones) == 1  # recurrence cloned next instance
    assert clones[0].deadline_date == date(2026, 8, 27)


def test_rm_with_dry_run(parser, service):
    execute("add", _args(parser, "add", "要删除的任务"), service)
    dry = execute("rm", _args(parser, "rm", "--match", "要删除", "--dry-run"), service)
    assert dry["type"] == "dry_run"
    r = execute("rm", _args(parser, "rm", "--match", "要删除"), service)
    assert r["count"] == 1 and len(service.get_all()) == 0


def test_archive_all(parser, service, repository):
    from src.models.task_filter import TaskFilter
    from src.models.task_status import TaskStatus

    repository.update_partition_archive_days(service.ensure_default_partition(), 30)
    execute("add", _args(parser, "add", "- [ ] TODO 未完成"), service)
    execute("add", _args(parser, "add", "- [x] DONE 已完成"), service)
    r = execute("archive", _args(parser, "archive", "--all"), service)
    assert r["count"] >= 1
    done = service.search(TaskFilter(statuses={TaskStatus.DONE}))
    assert all(t.archived for t in done)


# ------------------------------------------------------------------
# tags / partitions / recurrence / reminder / export
# ------------------------------------------------------------------

def test_tags_counts(parser, service):
    execute("add", _args(parser, "add", "任务一 #工作 #工作"), service)
    execute("add", _args(parser, "add", "任务二 #工作 #学习"), service)
    r = execute("tags", _args(parser, "tags", "--counts"), service)
    counts = {e["tag"]: e["count"] for e in r["tags"]}
    assert counts["工作"] == 2 and counts["学习"] == 1


def test_partitions_crud(parser, service):
    r = execute("partitions", _args(parser, "partitions", "--add", "读书"), service)
    pid = r["partition"]["id"]
    execute("partitions", _args(parser, "partitions", "--rename", pid, "阅读"), service)
    names = [p["name"] for p in execute("partitions", _args(parser, "partitions"), service)["partitions"]]
    assert "阅读" in names
    execute("partitions", _args(parser, "partitions", "--rm", pid), service)
    names = [p["name"] for p in execute("partitions", _args(parser, "partitions"), service)["partitions"]]
    assert "阅读" not in names


def test_recurrence_get_set(parser, service):
    execute("add", _args(parser, "add", "健身"), service)
    execute("recurrence", _args(parser, "recurrence", "--match", "健身", "--rule", "+1m"), service)
    r = execute("recurrence", _args(parser, "recurrence", "--match", "健身"), service)
    assert r["rule"] == "+1m"


def test_reminder_config(tmp_path: Path, parser, service):
    config = AppConfig(tmp_path)
    r = execute("reminder", _args(parser, "reminder"), service, config)
    assert r["type"] == "reminder"
    r = execute("reminder", _args(
        parser, "reminder", "--enable", "--digest-time", "08:30",
    ), service, config)
    assert r["enabled"] and r["daily_digest_time"] == "08:30"
    saved = AppConfig(tmp_path)
    assert saved.reminders_enabled and saved.reminder_daily_digest_time == "08:30"


def test_export_md_and_xlsx(tmp_path: Path, parser, service):
    execute("add", _args(parser, "add", "导出任务 #工作"), service)
    md_path = tmp_path / "out.md"
    r = execute("export", _args(parser, "export", "--fmt", "md", "--out", str(md_path)), service)
    assert r["count"] == 1 and md_path.exists() and "导出任务" in md_path.read_text(encoding="utf-8")
    xl_path = tmp_path / "out.xlsx"
    r = execute("export", _args(parser, "export", "--fmt", "xlsx", "--out", str(xl_path)), service)
    assert r["count"] == 1 and xl_path.exists() and xl_path.stat().st_size > 0


# ------------------------------------------------------------------
# output rendering
# ------------------------------------------------------------------

def test_render_json_and_human(parser, service):
    execute("add", _args(parser, "add", "渲染任务 #工作"), service)
    r = execute("list", _args(parser, "list"), service)
    assert json.loads(render(r, "json"))["count"] == 1
    human = render(r, "human")
    assert "渲染任务" in human and "#工作" in human


def test_report_week(parser, service, repository):
    """report 锚定单一分区聚合本周工作内容与下周计划，剔除噪声条目."""
    from datetime import datetime, timedelta

    pid = service.ensure_default_partition()
    repository.update_partition_archive_days(pid, 30)
    # 本周已动过的任务：带要点与噪声条目
    r = execute("add", _args(parser, "add", "- [x] DONE <2026-08-20> 报告任务A #工作"), service)
    task = service.get_task(r["task"]["id"])
    task.activity_log = list(task.activity_log or []) + [
        {"ts": datetime.now().isoformat(), "content": "完成初稿", "status": "DONE", "progress": 100},
        {"ts": datetime.now().isoformat(), "content": "[批量操作] 延后处理: 2026-08-20 -> 2026-08-21（+1天）",
         "status": "DONE", "progress": 100},
    ]
    service.update_task(task)
    # 期内创建的任务 → 本周工作内容（创建本身即本周工作）
    r_b = execute("add", _args(parser, "add", "- [ ] TODO <2026-08-21> 新建任务B #工作"), service)
    assert r_b["task"]["title"] == "新建任务B"
    # 期前遗留的未完成任务 → 下周计划（回拨 created_at 与活动时间戳）
    r_c = execute("add", _args(parser, "add", "- [ ] TODO <2026-08-21> 遗留任务C #工作"), service)
    task_c = service.get_task(r_c["task"]["id"])
    old = (datetime.now() - timedelta(days=10)).isoformat()
    task_c.created_at = datetime.fromisoformat(old)
    task_c.updated_at = datetime.fromisoformat(old)
    task_c.activity_log = [{"ts": old, "content": "创建任务", "status": "TODO", "progress": 0}]
    service.update_task(task_c)

    report = execute("report", _args(parser, "report"), service)
    assert report["type"] == "report" and report["period"] == "week"
    assert report["partition_id"] == pid  # 分区优先：锚定单一分区
    group = report["groups"][0]
    assert group["tag"] == "工作"
    worked = [i for i in group["worked"] if i["title"] == "报告任务A"][0]
    assert worked["points"] == ["完成初稿"]  # 批量操作/创建任务 已剔除
    worked_titles = [i["title"] for i in group["worked"]]
    assert "新建任务B" in worked_titles  # 期内创建 → 本周工作内容
    planned_titles = [i["title"] for i in group["planned"]]
    assert "遗留任务C" in planned_titles  # 期前遗留 → 下周计划
    assert "报告任务A" not in planned_titles and "新建任务B" not in planned_titles
    human = render(report, "human")
    assert "本周工作内容" in human and "下周工作计划" in human and "#工作" in human


def test_report_offset_last_week(parser, service):
    """--offset -1 覆盖上一周的活动."""
    from datetime import datetime, timedelta

    r = execute("add", _args(parser, "add", "上周任务"), service)
    task = service.get_task(r["task"]["id"])
    last_week = (datetime.now() - timedelta(days=7)).isoformat()
    task.activity_log = list(task.activity_log or []) + [
        {"ts": last_week, "content": "上周完成的工作", "status": "DOING", "progress": 40},
    ]
    service.update_task(task)
    current = execute("report", _args(parser, "report"), service)
    assert all("上周完成的工作" not in i["points"]
               for g in current["groups"] for i in g["worked"])
    previous = execute("report", _args(parser, "report", "--offset", "-1"), service)
    assert any("上周完成的工作" in i["points"]
               for g in previous["groups"] for i in g["worked"])


def test_activity_timeline(parser, service):
    """activity 返回指定日期的活动时间线（默认今天）."""
    from datetime import datetime

    today = date.today()
    now = datetime.now()
    execute("add", _args(parser, "add", "活动任务A"), service)
    task = execute("list", _args(parser, "list"), service)["tasks"][0]
    # 追加一条今日活动记录（模拟 GUI 追加进展）
    stored = service.get_task(task["id"])
    stored.activity_log.append({
        "ts": now.isoformat(), "content": "完成初稿", "status": "DOING", "progress": 50,
    })
    service.update_task(stored)
    r = execute("activity", _args(parser, "activity"), service)
    assert r["date"] == today.isoformat()
    assert r["entry_count"] == 2  # 创建 + 追加
    assert r["created"] == 1
    contents = [e["content"] for e in r["entries"]]
    assert "完成初稿" in contents and "创建任务" in contents
    human = render(r, "human")
    assert "活动任务A" in human and "完成初稿" in human
    # 指定日期无活动
    r2 = execute("activity", _args(parser, "activity", "--date", "2020-01-01"), service)
    assert r2["entry_count"] == 0


def test_log_command(parser, service, repository):
    """log 追加活动进展；--status DONE 同时完成任务."""
    repository.update_partition_archive_days(service.ensure_default_partition(), 30)
    execute("add", _args(parser, "add", "日志任务"), service)
    r = execute("log", _args(parser, "log", "--match", "日志任务",
                             "--content", "完成初稿", "--status", "DOING", "--progress", "50"), service)
    assert r["type"] == "activity_entry" and r["content"] == "完成初稿"
    task = service.get_task(r["task_id"])
    assert task.progress == 50 and any(e["content"] == "完成初稿" for e in task.activity_log)
    dry = execute("log", _args(parser, "log", "--match", "日志任务",
                               "--content", "终稿", "--dry-run"), service)
    assert dry["type"] == "dry_run"
    execute("log", _args(parser, "log", "--match", "日志任务",
                         "--content", "终稿", "--status", "DONE"), service)
    task = service.get_task(r["task_id"])
    assert task.status.value == "DONE"


def test_render_countdown(parser, service):
    """human 输出带倒计数：今天到期 / 剩 N 天 / 已逾期 N 天."""
    from datetime import date as _date
    from datetime import timedelta

    today = _date.today()
    execute("add", _args(parser, "add", f"- [ ] TODO <{today}> 当天任务"), service)
    execute("add", _args(parser, "add", f"- [ ] TODO <{today + timedelta(days=3)}> 三天后"), service)
    execute("add", _args(parser, "add", f"- [ ] TODO <{today - timedelta(days=2)}> 两天前"), service)
    human = render(execute("list", _args(parser, "list"), service), "human")
    assert "今天到期" in human
    assert "剩 3 天" in human
    assert "已逾期 2 天" in human


# ------------------------------------------------------------------
# pipe protocol + forwarding
# ------------------------------------------------------------------

def _fake_gui_server(name: str, respond: bool, ready: threading.Event,
                     captured: dict | None = None) -> None:
    """Worker thread: accept one connection, optionally answer a CLI request.

    The server side needs its own event loop — QLocalServer does not accept
    pending connections under blocking waits alone on Windows.
    ``captured`` receives the parsed request payload when provided.
    """

    def _run() -> None:
        from PySide6.QtCore import QEventLoop

        from src.cli.protocol import read_raw

        server = QLocalServer()
        server.removeServer(name)
        if not server.listen(name):
            ready.set()
            return
        ready.set()
        loop = QEventLoop()
        server.newConnection.connect(loop.quit)
        loop.exec()  # wait until the client connects
        conn = server.nextPendingConnection()
        if conn is None:
            return
        data = read_raw(conn, 3000)
        if respond and data.startswith(PROTO_HEADER):
            payload = json.loads(data[len(PROTO_HEADER):].decode("utf-8"))
            if captured is not None:
                captured.update(payload)
            # Responses are bare JSON — only requests carry the magic header.
            conn.write(json.dumps(
                {"ok": True, "result": {"type": "echo", "command": payload.get("command")}},
                ensure_ascii=False,
            ).encode("utf-8"))
        conn.flush()
        if conn.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            conn.waitForDisconnected(2000)  # client closes after reading
        conn.close()
        server.close()

    threading.Thread(target=_run, daemon=True).start()


def test_try_forward_round_trip(qapp, monkeypatch):
    name = "tadado_cli_test_1"
    monkeypatch.setattr("src.cli.forward.SERVER_NAME", name)
    ready = threading.Event()
    captured: dict = {}
    _fake_gui_server(name, respond=True, ready=ready, captured=captured)
    assert ready.wait(5)
    request = {"v": 1, "app": "0.2.7", "data_dir": "C:/x/resources",
               "command": "list", "args": {}}
    connected, response = try_forward(request)
    assert connected and response is not None
    assert response["ok"] and response["result"]["command"] == "list"
    # 请求帧携带身份信息（版本 + 数据目录），GUI 侧据此校验同一实例
    assert captured["app"] == "0.2.7"
    assert captured["data_dir"] == "C:/x/resources"


def test_validate_request_identity():
    """同一实例校验：版本/数据目录不匹配时报错."""
    from src.cli.protocol import validate_request

    base = {"v": 1, "app": "0.2.7", "data_dir": "C:/data/resources"}
    assert validate_request(base, "0.2.7", "C:/data/resources") is None
    # Windows 大小写不敏感路径
    assert validate_request(base, "0.2.7", "c:/DATA/RESOURCES") is None
    err = validate_request(base, "0.2.7", "C:/other/resources")
    assert "数据目录不一致" in err
    err = validate_request(base, "0.2.6", "C:/data/resources")
    assert "版本不一致" in err


def test_try_forward_legacy_gui_no_response(qapp, monkeypatch):
    """Legacy GUI (pre-protocol) consumes the request without answering."""
    name = "tadado_cli_test_2"
    monkeypatch.setattr("src.cli.forward.SERVER_NAME", name)
    ready = threading.Event()
    _fake_gui_server(name, respond=False, ready=ready)
    assert ready.wait(5)
    connected, response = try_forward({"v": 1, "command": "list", "args": {}})
    assert connected and response is None


def test_try_forward_no_server(qapp, monkeypatch):
    monkeypatch.setattr("src.cli.forward.SERVER_NAME", "tadado_cli_test_missing")
    connected, response = try_forward({"v": 1, "command": "list", "args": {}})
    assert not connected and response is None


# ------------------------------------------------------------------
# e2e subprocess
# ------------------------------------------------------------------

def _run_cli(*argv: str, data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["TADADO_DATA_DIR"] = str(data_dir)
    env["TADADO_NO_FORWARD"] = "1"
    return subprocess.run(
        [sys.executable, "main.py", "--cli", *argv],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )


def test_e2e_add_list_round_trip(tmp_path: Path):
    add = _run_cli("add", "- [*] TODO <2026-08-20> e2e任务 #工作", data_dir=tmp_path)
    assert add.returncode == 0, add.stderr
    task = json.loads(add.stdout)["task"]
    listing = _run_cli("list", "--keyword", "e2e", data_dir=tmp_path)
    assert listing.returncode == 0, listing.stderr
    result = json.loads(listing.stdout)
    assert result["total"] == 1
    assert result["tasks"][0]["id"] == task["id"]
    done = _run_cli("done", task["id"], data_dir=tmp_path)
    assert done.returncode == 0
    assert json.loads(done.stdout)["status"] == "DONE"


def test_e2e_error_exit_code(tmp_path: Path):
    bad = _run_cli("done", "--match", "不存在的任务xyz", data_dir=tmp_path)
    assert bad.returncode == 1
    assert "error" in bad.stderr

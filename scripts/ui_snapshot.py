"""Offscreen UI snapshot for design audit — saves key screens as PNGs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "qt.network.ssl.warning=false"
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer

from src.app import TadadoApp

app = TadadoApp(sys.argv, QLocalServer())
out = os.environ.get("SNAP_DIR", ".")


def _save(widget, name):
    try:
        widget.grab().save(os.path.join(out, name))
        print("SAVED", name)
    except Exception as e:
        print("GRAB ERR", name, e)


def snap():
    """抓图入口：任何异常都要落到 finally 退出事件循环，不能空转。"""
    try:
        _run_snaps()
    except Exception:
        import traceback

        traceback.print_exc()
        print("SNAP FAILED")
    finally:
        app._on_quit()


def _run_snaps():
    w = app.main_window
    _save(w, "ui_taskview_light.png")
    try:
        w._switch_view("dashboard")
        app.processEvents()
        _save(w, "ui_dashboard_light.png")
    except Exception as e:
        print("VIEW ERR dashboard", e)
    try:
        w._switch_view("batch")
        app.processEvents()
        _save(w, "ui_batch_light.png")
    except Exception as e:
        print("VIEW ERR batch", e)
    try:
        w._on_settings()
        app.processEvents()
        w.activateWindow()
        app.processEvents()
        _save(w, "ui_settings_light.png")
        w._settings_drawer.close_drawer()
    except Exception as e:
        print("VIEW ERR settings", e)


# 硬看门狗：抓图流程若卡住，也必须在 30s 内结束进程（offscreen 平台下
# 事件循环不会自己停下来，无上限等待会直接挂住 CI / 本地终端）。
QTimer.singleShot(30_000, lambda: (print("WATCHDOG TIMEOUT"), app.quit()))
QTimer.singleShot(4000, snap)
print("EXIT", app.exec())
sys.exit(0)

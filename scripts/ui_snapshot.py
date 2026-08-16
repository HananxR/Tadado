"""Offscreen UI snapshot for design audit — saves key screens as PNGs."""
import os, sys
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
        from src.ui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(app._config, app._repository, task_service=app._task_service)
        dlg.resize(640, 480)
        app.processEvents()
        _save(dlg, "ui_settings_light.png")
        dlg.close()
    except Exception as e:
        print("VIEW ERR settings", e)
    app._on_quit()


QTimer.singleShot(4000, snap)
sys.exit(app.exec())

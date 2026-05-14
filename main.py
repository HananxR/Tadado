# DeskTodoSeq — 入口

import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QMessageBox

from src.app import DeskTodoSeqApp

_SERVER_NAME = "DeskTodoSeq_Instance"


def main() -> None:
    QLocalServer.removeServer(_SERVER_NAME)
    local_server = QLocalServer()
    if not local_server.listen(_SERVER_NAME):
        # Another instance is running — wake it and exit
        sock = QLocalSocket()
        sock.connectToServer(_SERVER_NAME)
        if sock.waitForConnected(2000):
            sock.write(b"wake")
            sock.waitForBytesWritten(1000)
            sock.close()
        QMessageBox.information(None, "DeskTodoSeq", "软件已在运行，已切换至已有窗口。")
        sys.exit(0)

    app = DeskTodoSeqApp(sys.argv, local_server)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

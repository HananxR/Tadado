# Tadado — 入口

import os
import sys

os.environ["QT_LOGGING_RULES"] = "qt.network.ssl.warning=false"

from PySide6.QtNetwork import QLocalServer, QLocalSocket

from src.app import TadadoApp

_SERVER_NAME = "Tadado_Instance"


def main() -> None:
    # Step 1: Try connecting to an existing instance first
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    if sock.waitForConnected(500):
        # Another instance is running — wake it and exit silently
        sock.write(b"wake")
        sock.waitForBytesWritten(1000)
        sock.close()
        sys.exit(0)

    # Step 2: No existing instance — clean up stale pipe and start server
    QLocalServer.removeServer(_SERVER_NAME)
    local_server = QLocalServer()
    if not local_server.listen(_SERVER_NAME):
        # Race condition: another instance started between our check and listen
        sock2 = QLocalSocket()
        sock2.connectToServer(_SERVER_NAME)
        if sock2.waitForConnected(2000):
            sock2.write(b"wake")
            sock2.waitForBytesWritten(1000)
            sock2.close()
        sys.exit(0)

    app = TadadoApp(sys.argv, local_server)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

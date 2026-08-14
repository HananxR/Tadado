"""Forward CLI requests to a running Tadado GUI instance."""

from __future__ import annotations

from PySide6.QtNetwork import QLocalSocket

from .protocol import SERVER_NAME, read_message, write_message


def try_forward(request: dict, connect_timeout_ms: int = 800) -> tuple[bool, dict | None]:
    """Forward a request to the running GUI over the local pipe.

    Returns ``(connected, response)``.  ``response`` is None when a legacy
    GUI (pre-CLI) consumed the request without answering — the caller should
    report a "version too old" error instead of falling back to headless
    (two writers to the same database must never run at once).
    """
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(connect_timeout_ms):
        sock.close()
        return False, None
    write_message(sock, request)
    # No waitForBytesWritten here: on Windows named pipes it can burn the
    # timeout without confirming, and any delay before reading risks losing
    # the response when the server closes the pipe. Start reading at once.
    response = read_message(sock, 3000)
    sock.disconnectFromServer()
    if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        sock.waitForDisconnected(500)
    sock.close()
    return True, response

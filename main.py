# DeskTodoSeq — 入口

import sys

from src.app import DeskTodoSeqApp


def main() -> None:
    app = DeskTodoSeqApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

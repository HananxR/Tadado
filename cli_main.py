# tadado-cli 入口 — 始终进入 CLI 网关，不启动 GUI

import os
import sys

os.environ["QT_LOGGING_RULES"] = "qt.network.ssl.warning=false"

from src.cli.headless import run_cli


def main() -> None:
    sys.exit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()

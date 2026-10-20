"""统一入口：`python -m app [端口]`。

默认端口 8210（不占用 8094 / 8096 / 8193 / 8197 / 8207）。
只监听 127.0.0.1。
"""

from __future__ import annotations

import sys

from .server import run

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8210
    run(port=port)

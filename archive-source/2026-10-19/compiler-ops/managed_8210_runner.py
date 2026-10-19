"""Silent Task Scheduler entrypoint for the independent 8210 compiler.

This wrapper lives outside the frozen app/ source and only routes logs; it does
not alter compiler code, settings, or state.  The formal start.ps1 remains
available for an interactive standalone launch.
"""
from __future__ import annotations

import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "managed-8210.log"
STOP_MARKER = ROOT / "data" / "managed-8210.stop"
LOG.parent.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

_stream = LOG.open("a", encoding="utf-8", buffering=1)
sys.stdout = _stream
sys.stderr = _stream
print(f"[{datetime.now().astimezone().isoformat()}] managed 8210 starting pid={os.getpid()} cwd={ROOT}")

try:
    from app import server as server_module

    class ManagedServer(server_module.Server):
        active = None

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            type(self).active = self

    # The frozen server remains untouched. The wrapper adds a private, local
    # graceful-stop signal so Task Scheduler can manage this background runner.
    server_module.Server = ManagedServer
    stopping = threading.Event()

    def wait_for_stop() -> None:
        while not stopping.wait(0.25):
            if STOP_MARKER.exists() and ManagedServer.active is not None:
                try:
                    STOP_MARKER.unlink()
                except OSError:
                    continue
                print(f"[{datetime.now().astimezone().isoformat()}] graceful stop requested")
                ManagedServer.active.shutdown()
                return

    watcher = threading.Thread(target=wait_for_stop, name="h3-8210-stop-signal", daemon=True)
    watcher.start()

    server_module.run(host="127.0.0.1", port=8210)
except BaseException:
    traceback.print_exc(file=_stream)
    raise
finally:
    if "stopping" in locals():
        stopping.set()
    print(f"[{datetime.now().astimezone().isoformat()}] managed 8210 exited pid={os.getpid()}")
    _stream.flush()
    _stream.close()

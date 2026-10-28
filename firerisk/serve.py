"""Start the FireRisk Intelligence dashboard:  python -m firerisk.serve  -> http://127.0.0.1:8765

Logs go to data/private/logs/firerisk.log (rotating, never contains keys or tokens). The console shows only
warnings and errors: fewer console writes means a paused Windows console (QuickEdit "Select" mode) cannot stall
the dashboard as easily. Crashes of Python itself are written to data/private/logs/crash.log.
"""

import copy
import faulthandler
import logging
import logging.config
import os
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.environ.get("FIRERISK_LOG_DIR", ROOT / "data" / "private" / "logs"))


def log_config() -> dict:
    from uvicorn.config import LOGGING_CONFIG
    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg["formatters"]["file"] = {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}
    cfg["handlers"]["file"] = {"class": "logging.handlers.RotatingFileHandler", "formatter": "file",
                               "filename": str(LOG_DIR / "firerisk.log"), "maxBytes": 2_000_000, "backupCount": 3,
                               "encoding": "utf-8"}
    cfg["handlers"]["default"]["level"] = "WARNING"
    cfg["loggers"]["uvicorn"]["handlers"] = ["default", "file"]
    cfg["loggers"]["uvicorn.access"]["handlers"] = ["file"]          # request lines: file only
    cfg["loggers"]["firerisk"] = {"handlers": ["default", "file"], "level": "INFO", "propagate": False}
    return cfg


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    crash = open(LOG_DIR / "crash.log", "a", encoding="utf-8")
    faulthandler.enable(crash)
    log = logging.getLogger("firerisk")

    def on_thread_error(args):
        log.error("unhandled error in thread %s", args.thread.name if args.thread else "?",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = on_thread_error
    sys.excepthook = lambda t, v, tb: log.critical("unhandled error", exc_info=(t, v, tb))

    port = int(os.environ.get("FIRERISK_PORT", "8765"))
    logging.config.dictConfig(log_config())
    log.info("starting FireRisk Intelligence on port %s", port)
    from .api import start_auto_sync
    if start_auto_sync():
        print("Automatic updates from Google Drive: on")
    print(f"Dashboard: http://127.0.0.1:{port}  (keep this window open; do not click inside it)")
    if os.environ.get("FIRERISK_NO_BROWSER") != "1":
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        uvicorn.run("firerisk.api:app", host="127.0.0.1", port=port, log_config=log_config())
    finally:
        log.info("dashboard stopped")


if __name__ == "__main__":
    main()

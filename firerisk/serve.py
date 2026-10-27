"""Start the FireRisk Intelligence dashboard:  python -m firerisk.serve  -> http://127.0.0.1:8765"""

import os
import webbrowser

import uvicorn


def main() -> None:
    port = int(os.environ.get("FIRERISK_PORT", "8765"))
    if os.environ.get("FIRERISK_NO_BROWSER") != "1":
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run("firerisk.api:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()

# backend/run_backend.py
"""
Backend launcher for the desktop packaged app.

Intercepts custom command-line arguments (--data-dir, --storage-path) before
delegating to uvicorn.  Docker and start.bat continue to use `python -m uvicorn`
directly and are unaffected by this script.

Usage (from electron main process):
    python backend/run_backend.py backend.main:app \
        --host 127.0.0.1 --port 8000 \
        --data-dir C:/Users/.../AppData/.../data \
        --storage-path C:/Users/.../AppData/.../data/uploads
"""

import sys


def main() -> None:
    # ── Parse & strip custom arguments ──────────────────────────────────
    custom: dict[str, str] = {}
    clean_argv = [sys.argv[0]]
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ("--data-dir", "--storage-path") and i + 1 < len(sys.argv):
            custom[arg] = sys.argv[i + 1]
            i += 2
        else:
            clean_argv.append(arg)
            i += 1

    # Store in _cli_args module so downstream code (database.py,
    # storage_service.py) can import them directly — no env vars.
    if "--data-dir" in custom or "--storage-path" in custom:
        import backend._cli_args

        backend._cli_args.DATA_DIR = custom.get("--data-dir")
        backend._cli_args.STORAGE_PATH = custom.get("--storage-path")

    # Replace argv so uvicorn / click only see the args they understand.
    sys.argv = clean_argv

    # ── Delegate to uvicorn ─────────────────────────────────────────────
    import uvicorn

    uvicorn.main()


if __name__ == "__main__":
    main()

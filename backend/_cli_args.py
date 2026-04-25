# backend/_cli_args.py
"""
Stores data-directory arguments parsed from the command line by run_backend.py.

Only the desktop packaged app uses this mechanism.  Docker and start.bat call
`python -m uvicorn` directly, so these values remain None and every consumer
falls back to its default behaviour.
"""

__all__ = ["DATA_DIR", "STORAGE_PATH"]

DATA_DIR: str | None = None
STORAGE_PATH: str | None = None

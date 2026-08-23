"""支持 python -m backend.mambo_cli 运行。"""
import sys

from backend.mambo_cli.main import main

if __name__ == "__main__":
    sys.exit(main())

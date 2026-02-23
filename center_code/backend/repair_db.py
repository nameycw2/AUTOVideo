"""入口：从 backend 目录执行 python repair_db.py 或 python -m scripts.repair_db"""
import sys
from scripts.repair_db import main
sys.exit(main())

from pathlib import Path

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).parent.parent.parent.resolve()

Path(BASE_DIR / "cookies" / "kuaishou_uploader").mkdir(parents=True, exist_ok=True)

from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()
DATA_DIR = Path(os.getenv("RAGX_DATA_DIR", PROJECT_ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
VECTOR_DIR = DATA_DIR / "vectors"
SQLITE_DIR = DATA_DIR / "sqlite"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def ensure_data_dirs() -> None:
    for path in (DATA_DIR, UPLOAD_DIR, VECTOR_DIR, SQLITE_DIR):
        path.mkdir(parents=True, exist_ok=True)

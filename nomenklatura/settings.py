from pathlib import Path
from rigour.env import env_str

TESTING = False

DB_PATH = Path("nomenklatura.db").resolve()
DB_URL = env_str("NOMENKLATURA_DB_URL", f"sqlite:///{DB_PATH.as_posix()}")
DB_POOL_SIZE = int(env_str("NOMENKLATURA_DB_POOL_SIZE", "5"))

REDIS_URL = env_str("NOMENKLATURA_REDIS_URL", "")

STATEMENT_TABLE = env_str("NOMENKLATURA_STATEMENT_TABLE", "statement")
STATEMENT_BATCH = int(env_str("NOMENKLATURA_STATEMENT_BATCH", "10000"))

from pathlib import Path
from rigour.env import env_str, env_int

TESTING = False

DB_PATH = Path("nomenklatura.db").resolve()
DEFAULT_DB_URL = f"sqlite:///{DB_PATH.as_posix()}"
DB_URL = env_str("NOMENKLATURA_DB_URL", "")
if DB_URL is None or not len(DB_URL):
    DB_URL = DEFAULT_DB_URL
DB_POOL_SIZE = env_int("NOMENKLATURA_DB_POOL_SIZE", 5)
DB_STMT_TIMEOUT = env_int("NOMENKLATURA_DB_STMT_TIMEOUT", 10000)

REDIS_URL = env_str("NOMENKLATURA_REDIS_URL", "")

STATEMENT_TABLE = env_str("NOMENKLATURA_STATEMENT_TABLE", "statement")
STATEMENT_BATCH = env_int("NOMENKLATURA_STATEMENT_BATCH", 3000)

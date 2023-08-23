from os import environ as env
from pathlib import Path
from normality import stringify


def env_str(name: str, default: str) -> str:
    """Ensure the env returns a string even on Windows (#100)."""
    value = stringify(env.get(name))
    return default if value is None else value


DB_PATH = Path("nomenklatura.db").resolve()
DB_URL = env_str("NOMENKLATURA_DB_URL", f"sqlite:///{DB_PATH.as_posix()}")
DB_POOL_SIZE = int(env_str("NOMENKLATURA_DB_POOL_SIZE", "5"))

STATEMENT_TABLE = env_str("NOMENKLATURA_STATEMENT_TABLE", "statement")
STATEMENT_BATCH = int(env_str("NOMENKLATURA_STATEMENT_BATCH", "10000"))

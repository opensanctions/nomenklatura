import asyncio
from pathlib import Path
from functools import wraps
from typing import Any

PathLike = Path  # like


def coro(f: Any) -> Any:
    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))

    return wrapper

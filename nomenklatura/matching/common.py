import re
from typing import List, Set, TypeVar


V = TypeVar("V")
FIND_NUM = re.compile("\d{2,}")


def extract_numbers(values: List[str]) -> Set[str]:
    numbers: Set[str] = set()
    for value in values:
        numbers.update(FIND_NUM.findall(value))
    return numbers

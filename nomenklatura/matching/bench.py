import datetime
from timeit import timeit
from itertools import cycle
import logging

from nomenklatura.matching import get_algorithm
from nomenklatura.matching.pairs import read_pairs
from nomenklatura.util import PathLike


log = logging.getLogger(__name__)


def bench_matcher(name: str, pairs_file: PathLike, number: int) -> None:
    log.info("Loading pairs from %s", pairs_file)
    pairs = list(read_pairs(pairs_file))
    log.info("Read %d pairs", len(pairs))
    matcher = get_algorithm(name)
    if matcher is None:
        raise ValueError("No matcher named %s", name)
    log.info("Loaded %s", matcher.NAME)
    infinite_pairs = cycle(pairs)

    def compare_one_pair() -> None:
        pair = next(infinite_pairs)
        matcher.compare(pair.left, pair.right)

    log.info("Running benchmark for %d iterations", number)
    seconds = timeit(compare_one_pair, number=number)
    log.info("Total time %s", datetime.timedelta(seconds=seconds))

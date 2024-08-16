import datetime
from timeit import timeit
from itertools import cycle

from nomenklatura.matching import get_algorithm
from nomenklatura.matching.pairs import read_pairs
from nomenklatura.util import PathLike


def bench_matcher(name: str, pairs_file: PathLike, number: int) -> None:
    print("Loading pairs from %s" % pairs_file)
    pairs = list(read_pairs(pairs_file))
    print("Read %d pairs" % len(pairs))
    matcher = get_algorithm(name)
    print("Loaded %s" % matcher.NAME)
    infinite_pairs = cycle(pairs)

    def compare_one_pair():
        pair = next(infinite_pairs)
        matcher.compare(pair.left, pair.right)

    print("Running benchmark for %d iterations" % number)
    seconds = timeit(compare_one_pair, number=number)
    print(datetime.timedelta(seconds=seconds))

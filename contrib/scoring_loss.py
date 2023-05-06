import math
import click
from typing import Dict, Generator, Tuple
from pathlib import Path
from zavod.logs import get_logger, configure_logging
from nomenklatura.judgement import Judgement
from nomenklatura.matching import ALGORITHMS
from nomenklatura.matching.pairs import read_pairs
from followthemoney.cli.util import InPath

log = get_logger("scoring_loss")


@click.command()
@click.argument("source_path", type=InPath)
def process_pairs(source_path: Path):
    configure_logging()

    total: int = 0
    losses: Dict[str, float] = {a.NAME: 0.0 for a in ALGORITHMS}
    for pair in read_pairs(source_path):
        if pair.judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
            continue
        total += 1
        if total % 10000 == 0:
            log.info("Processed %s pairs..." % total)
        value = 1.0 if pair.judgement == Judgement.POSITIVE else 0.0
        for algorithm in ALGORITHMS:
            score = algorithm.compare(pair.left, pair.right)
            loss = math.fabs(value - score["score"])
            losses[algorithm.NAME] += loss

    for algorithm in ALGORITHMS:
        log.info("%s: %s" % (algorithm.NAME, losses[algorithm.NAME] / total))


if __name__ == "__main__":
    process_pairs()

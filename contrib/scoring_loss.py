import math
import click
from typing import Dict, Type, List
from pathlib import Path
from zavod.logs import get_logger, configure_logging
from nomenklatura.judgement import Judgement
from nomenklatura.matching import MatcherV1, NameMatcher, NameQualifiedMatcher, LogicV1
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.matching.pairs import read_pairs
from followthemoney.cli.util import InPath

log = get_logger("scoring_loss")

ALGORITHMS: List[Type[ScoringAlgorithm]] = [
    MatcherV1,
    # MatcherV2,
    NameMatcher,
    NameQualifiedMatcher,
    LogicV1,
]


@click.command()
@click.argument("source_path", type=InPath)
def process_pairs(source_path: Path):
    configure_logging()

    total: int = 0
    threshold: float = 0.7
    losses: Dict[str, float] = {a.NAME: 0.0 for a in ALGORITHMS}
    matrix: Dict[str, dict] = {a.NAME: {} for a in ALGORITHMS}
    for pair in read_pairs(source_path):
        if pair.judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
            continue
        total += 1
        if total % 10000 == 0:
            log.info("Processed %s pairs..." % total)
        value = 1.0 if pair.judgement == Judgement.POSITIVE else 0.0
        for algorithm in ALGORITHMS:
            name = algorithm.NAME
            score = algorithm.compare(pair.left, pair.right)
            loss = math.fabs(value - score.score)
            losses[name] += loss

            decision = (pair.judgement, Judgement.NEGATIVE)
            if score.score >= threshold:
                decision = (pair.judgement, Judgement.POSITIVE)

            matrix[name][decision] = matrix[name].get(decision, 0) + 1

    for algorithm in ALGORITHMS:
        log.info("---------------------------------")
        log.info("%s: %s" % (algorithm.NAME, losses[algorithm.NAME] / total))
        algo_matrix = matrix.get(algorithm.NAME, {})
        true_neg = algo_matrix.get((Judgement.NEGATIVE, Judgement.NEGATIVE), 0)
        true_pos = algo_matrix.get((Judgement.POSITIVE, Judgement.POSITIVE), 0)
        false_pos = algo_matrix.get((Judgement.NEGATIVE, Judgement.POSITIVE), 0)
        false_neg = algo_matrix.get((Judgement.POSITIVE, Judgement.NEGATIVE), 0)
        total = true_pos + true_neg + false_pos + false_neg

        log.info("True match: %s" % (true_pos + true_neg))
        log.info("False positive: %s" % false_pos)
        log.info("False negative: %s" % false_neg)
        fail_pct = float(false_neg + false_pos) / float(total)
        log.info("Fail %%: %s" % (fail_pct * 100))


if __name__ == "__main__":
    process_pairs()

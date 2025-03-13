import os
import shutil
import yaml
import click
import logging
from pathlib import Path
from typing import Generator, List, Optional, Tuple
from followthemoney.cli.util import path_writer, InPath, OutPath
from followthemoney.cli.util import path_entities, write_entity
from followthemoney.cli.aggregate import sorted_aggregate

from nomenklatura.cache import Cache
from nomenklatura.matching import train_v1_matcher
from nomenklatura.store import load_entity_file_store
from nomenklatura.resolver import Resolver
from nomenklatura.dataset import Dataset, DefaultDataset
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.enrich import Enricher, make_enricher, match, enrich
from nomenklatura.statement import Statement, CSV, FORMATS
from nomenklatura.matching import get_algorithm, DefaultAlgorithm
from nomenklatura.statement import write_statements, read_path_statements
from nomenklatura.stream import StreamEntity
from nomenklatura.xref import xref as run_xref
from nomenklatura.tui import dedupe_ui
from nomenklatura.matching.bench import bench_matcher

INDEX_SEGMENT = "xref-index"

log = logging.getLogger(__name__)

ResPath = click.Path(dir_okay=False, writable=True, path_type=Path)


def _path_sibling(path: Path, suffix: str) -> Path:
    return path.parent.joinpath(f"{path.stem}{suffix}")


def _load_enricher(path: Path) -> Tuple[Dataset, Enricher[Dataset]]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
        dataset = Dataset.make(data)
        cache = Cache.make_default(dataset)
        enricher = make_enricher(dataset, cache, data)
        if enricher is None:
            raise TypeError("Could not load enricher")
        return dataset, enricher


@click.group(help="Nomenklatura data integration")
def cli() -> None:
    logging.basicConfig(level=logging.INFO)


@cli.command("xref", help="Generate dedupe candidates")
@click.argument("path", type=InPath)
@click.option("-a", "--auto-threshold", type=click.FLOAT, default=None)
@click.option("-l", "--limit", type=click.INT, default=5000)
@click.option("--algorithm", default=DefaultAlgorithm.NAME)
@click.option("--scored/--unscored", is_flag=True, type=click.BOOL, default=True)
@click.option(
    "-c",
    "--clear",
    is_flag=True,
    default=False,
    help="Clear the index directory, if it exists.",
)
def xref_file(
    path: Path,
    auto_threshold: Optional[float] = None,
    algorithm: str = DefaultAlgorithm.NAME,
    limit: int = 5000,
    scored: bool = True,
    clear: bool = False,
) -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    store = load_entity_file_store(path, resolver=resolver)
    algorithm_type = get_algorithm(algorithm)
    if algorithm_type is None:
        raise click.Abort(f"Unknown algorithm: {algorithm}")

    index_dir = Path(
        os.environ.get("NOMENKLATURA_INDEX_PATH", path.parent / INDEX_SEGMENT)
    )
    if clear and index_dir.exists():
        log.info("Clearing index: %s", index_dir)
        shutil.rmtree(index_dir, ignore_errors=True)
    run_xref(
        resolver,
        store,
        index_dir,
        auto_threshold=auto_threshold,
        algorithm=algorithm_type,
        scored=scored,
        limit=limit,
    )
    resolver.commit()
    log.info("Xref complete in: %r", resolver)


@cli.command("prune", help="Remove dedupe candidates")
def xref_prune() -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    resolver.prune()
    resolver.commit()


@cli.command("apply", help="Apply resolver to an entity stream")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option(
    "-d",
    "--dataset",
    type=str,
    default=None,
    help="Add a dataset to the entity metadata",
)
def apply(path: Path, outpath: Path, dataset: Optional[str] = None) -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    linker = resolver.get_linker()
    resolver.rollback()
    with path_writer(outpath) as outfh:
        for proxy in path_entities(path, StreamEntity):
            proxy = linker.apply_stream(proxy)
            if dataset is not None:
                proxy.datasets.add(dataset)
            write_entity(outfh, proxy)


@cli.command("sorted-aggregate", help="Merge sort-order entities")
@click.option("-i", "--infile", type=InPath, default="-")
@click.option("-o", "--outfile", type=OutPath, default="-")
def sorted_aggregate_(infile: Path, outfile: Path) -> None:
    sorted_aggregate(infile, outfile, StreamEntity)


@cli.command("make-sortable", help="Convert entities into plain-text sortable form")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
def make_sortable(path: Path, outpath: Path) -> None:
    with path_writer(outpath) as outfh:
        for entity in path_entities(path, Entity):
            write_entity(outfh, entity)


@cli.command("dedupe", help="Interactively judge xref candidates")
@click.argument("path", type=InPath)
@click.option("-x", "--xref", is_flag=True, default=False)
def dedupe(path: Path, xref: bool = False) -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    store = load_entity_file_store(path, resolver=resolver)
    if xref:
        index_dir = path.parent / INDEX_SEGMENT
        run_xref(resolver, store, index_dir)
    resolver.commit()

    dedupe_ui(resolver, store)


@cli.command("train-v1-matcher", help="Train a matching model from judgement pairs")
@click.argument("pairs_file", type=InPath)
def train_v1_matcher_(pairs_file: Path) -> None:
    train_v1_matcher(pairs_file)


@cli.command("match", help="Generate matches from an enrichment source")
@click.argument("config", type=InPath)
@click.argument("entities", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
def match_command(
    config: Path,
    entities: Path,
    outpath: Path,
) -> None:
    resolver = Resolver[Entity].make_default()
    _, enricher = _load_enricher(config)

    try:
        resolver.begin()
        with path_writer(outpath) as fh:
            stream = path_entities(entities, Entity)
            for proxy in match(enricher, resolver, stream):
                write_entity(fh, proxy)
        resolver.commit()
    finally:
        enricher.close()


@cli.command("enrich", help="Fetch extra info from an enrichment source")
@click.argument("config", type=InPath)
@click.argument("entities", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")  # noqa
def enrich_command(
    config: Path,
    entities: Path,
    outpath: Path,
) -> None:
    resolver = Resolver[Entity].make_default()
    _, enricher = _load_enricher(config)
    try:
        resolver.begin()
        with path_writer(outpath) as fh:
            stream = path_entities(entities, Entity)
            for proxy in enrich(enricher, resolver, stream):
                write_entity(fh, proxy)
        resolver.commit()
    finally:
        enricher.close()


@cli.command("statements", help="Export entities to statements")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-d", "--dataset", type=str, required=True)
@click.option("-f", "--format", type=click.Choice(FORMATS), default=CSV)
def entity_statements(path: Path, outpath: Path, dataset: str, format: str) -> None:
    def make_statements() -> Generator[Statement, None, None]:
        for entity in path_entities(path, Entity):
            yield from Statement.from_entity(entity, dataset=dataset)

    with path_writer(outpath) as outfh:
        write_statements(outfh, format, make_statements())


@cli.command("apply-statements", help="Apply a resolver file to a set of statements")
@click.option("-i", "--infile", type=InPath, default="-")
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-f", "--format", type=click.Choice(FORMATS), default=CSV)
def statements_apply(infile: Path, outpath: Path, format: str) -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    linker = resolver.get_linker()
    resolver.rollback()

    def _generate() -> Generator[Statement, None, None]:
        for stmt in read_path_statements(infile, format=format):
            yield linker.apply_statement(stmt)

    with path_writer(outpath) as outfh:
        write_statements(outfh, format, _generate())


@cli.command("format-statements", help="Convert entity data formats")
@click.option("-i", "--infile", type=InPath, default="-")
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-f", "--in-format", type=click.Choice(FORMATS), default=CSV)
@click.option("-x", "--out-format", type=click.Choice(FORMATS), default=CSV)
def format_statements(
    infile: Path, outpath: Path, in_format: str, out_format: str
) -> None:
    statements = read_path_statements(infile, format=in_format)
    with path_writer(outpath) as outfh:
        write_statements(outfh, out_format, statements)


@cli.command("aggregate-statements", help="Roll up statements into entities")
@click.option("-i", "--infile", type=InPath, default="-")
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-d", "--dataset", type=str, default=DefaultDataset.name)
@click.option("-f", "--format", type=click.Choice(FORMATS), default=CSV)
def statements_aggregate(
    infile: Path, outpath: Path, dataset: str, format: str
) -> None:
    dataset_ = Dataset.make({"name": dataset, "title": dataset})
    with path_writer(outpath) as outfh:
        statements: List[Statement] = []
        for stmt in read_path_statements(infile, format=format):
            if len(statements) and statements[0].canonical_id != stmt.canonical_id:
                entity = Entity.from_statements(dataset_, statements)
                write_entity(outfh, entity)
                statements = []
            statements.append(stmt)
        if len(statements):
            entity = Entity.from_statements(dataset_, statements)
            write_entity(outfh, entity)


@cli.command("load-resolver", help="Load resolver edges from file into database")
@click.argument("source", type=InPath)
def load_resolver(source: Path) -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    resolver.load(source)
    resolver.commit()


@cli.command("dump-resolver", help="Dump resolver decisions from database to file")
@click.argument("target", type=OutPath)
def dump_resolver(target: Path) -> None:
    resolver = Resolver[Entity].make_default()
    resolver.begin()
    resolver.dump(target)
    resolver.rollback()


@cli.command("bench", help="Benchmark a matching algorithm")
@click.argument("name", type=str)
@click.argument("pairs_file", type=InPath)
@click.option("-n", "--number", type=int, default=1000)
def bench(name: str, pairs_file: Path, number: int = 1000) -> None:
    bench_matcher(name, pairs_file, number)


if __name__ == "__main__":
    cli()

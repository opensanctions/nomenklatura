import orjson
import yaml
import click
import logging
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Tuple
from followthemoney.cli.util import path_writer, InPath, OutPath
from followthemoney.cli.util import path_entities, write_entity
from followthemoney.cli.aggregate import sorted_aggregate

from nomenklatura.cache import Cache
from nomenklatura.matching import train_v2_matcher, train_v1_matcher
from nomenklatura.store import load_entity_file_store
from nomenklatura.resolver import Resolver
from nomenklatura.dataset import Dataset, DefaultDataset
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.enrich import Enricher, make_enricher, match, enrich
from nomenklatura.statement import Statement, CSV, FORMATS
from nomenklatura.matching import get_algorithm, DefaultAlgorithm
from nomenklatura.statement import write_statements, read_path_statements
from nomenklatura.stream import StreamEntity
from nomenklatura.senzing import senzing_record
from nomenklatura.xref import xref as run_xref
from nomenklatura.tui import dedupe_ui


log = logging.getLogger(__name__)

ResPath = click.Path(dir_okay=False, writable=True, path_type=Path)


def _path_sibling(path: Path, suffix: str) -> Path:
    return path.parent.joinpath(f"{path.stem}{suffix}")


def _load_enricher(path: Path) -> Tuple[Dataset, Enricher]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
        dataset = Dataset.make(data)
        cache = Cache.make_default(dataset)
        enricher = make_enricher(dataset, cache, data)
        if enricher is None:
            raise TypeError("Could not load enricher")
        return dataset, enricher


def _get_resolver(file_path: Path, resolver_path: Optional[Path]) -> Resolver[Entity]:
    path = resolver_path or _path_sibling(file_path, ".rslv.ijson")
    return Resolver[Entity].load(Path(path))


@click.group(help="Nomenklatura data integration")
def cli() -> None:
    logging.basicConfig(level=logging.INFO)


@cli.command("xref", help="Generate dedupe candidates")
@click.argument("path", type=InPath)
@click.option("-r", "--resolver", type=ResPath)
@click.option("-a", "--auto-threshold", type=click.FLOAT, default=None)
@click.option("-l", "--limit", type=click.INT, default=5000)
@click.option("--algorithm", default=DefaultAlgorithm.NAME)
@click.option("--scored/--unscored", is_flag=True, type=click.BOOL, default=True)
def xref_file(
    path: Path,
    resolver: Optional[Path] = None,
    auto_threshold: Optional[float] = None,
    algorithm: str = DefaultAlgorithm.NAME,
    limit: int = 5000,
    scored: bool = True,
) -> None:
    resolver_ = _get_resolver(path, resolver)
    store = load_entity_file_store(path, resolver=resolver_)
    algorithm_type = get_algorithm(algorithm)
    if algorithm_type is None:
        raise click.Abort(f"Unknown algorithm: {algorithm}")
    run_xref(
        store,
        auto_threshold=auto_threshold,
        algorithm=algorithm_type,
        scored=scored,
        limit=limit,
    )
    resolver_.save()
    log.info("Xref complete in: %s", resolver_.path)


@cli.command("prune", help="Remove dedupe candidates")
@click.argument("resolver", type=ResPath)
def xref_prune(resolver: Path) -> None:
    resolver_ = _get_resolver(resolver, resolver)
    resolver_.prune()
    resolver_.save()


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
@click.option("-r", "--resolver", required=True, type=ResPath)
def apply(
    path: Path, outpath: Path, resolver: Optional[Path], dataset: Optional[str] = None
) -> None:
    resolver_ = _get_resolver(path, resolver)
    with path_writer(outpath) as outfh:
        for proxy in path_entities(path, StreamEntity):
            proxy = resolver_.apply_stream(proxy)
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
@click.option("-r", "--resolver", type=ResPath)
def dedupe(path: Path, xref: bool = False, resolver: Optional[Path] = None) -> None:
    resolver_ = _get_resolver(path, resolver)
    store = load_entity_file_store(path, resolver=resolver_)
    if xref:
        run_xref(store)

    dedupe_ui(store)
    resolver_.save()


@cli.command("merge-resolver", help="Merge resolver configs")
@click.argument("outpath", type=OutPath)
@click.option("-i", "--inputs", type=InPath, multiple=True)
def merge_resolver(outpath: Path, inputs: Iterable[Path]) -> None:
    resolver = Resolver[Entity].load(outpath)
    for path in inputs:
        resolver.merge(path)
    resolver.save()


@cli.command("train-v1-matcher", help="Train a matching model from judgement pairs")
@click.argument("pairs_file", type=InPath)
def train_v1_matcher_(pairs_file: Path) -> None:
    train_v1_matcher(pairs_file)


@cli.command("train-v2-matcher", help="Train a matching model from judgement pairs")
@click.argument("pairs_file", type=InPath)
def train_v2_matcher_(pairs_file: Path) -> None:
    train_v2_matcher(pairs_file)


@cli.command("match", help="Generate matches from an enrichment source")
@click.argument("config", type=InPath)
@click.argument("entities", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-r", "--resolver", type=ResPath)
def match_command(
    config: Path,
    entities: Path,
    outpath: Path,
    resolver: Optional[Path],
) -> None:
    resolver_ = _get_resolver(entities, resolver)
    _, enricher = _load_enricher(config)
    try:
        with path_writer(outpath) as fh:
            stream = path_entities(entities, Entity)
            for proxy in match(enricher, resolver_, stream):
                write_entity(fh, proxy)
    finally:
        resolver_.save()
        enricher.close()


@cli.command("enrich", help="Fetch extra info from an enrichment source")
@click.argument("config", type=InPath)
@click.argument("entities", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")  # noqa
@click.option("-r", "--resolver", type=ResPath)
def enrich_command(
    config: Path,
    entities: Path,
    outpath: Path,
    resolver: Optional[Path],
) -> None:
    resolver_ = _get_resolver(entities, resolver)
    _, enricher = _load_enricher(config)
    try:
        with path_writer(outpath) as fh:
            stream = path_entities(entities, Entity)
            for proxy in enrich(enricher, resolver_, stream):
                write_entity(fh, proxy)
    finally:
        enricher.close()


@cli.command("export-senzing", help="Export entities to Senzing API format")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-d", "--dataset", type=str, required=True)
def export_senzing(path: Path, outpath: Path, dataset: str) -> None:
    with path_writer(outpath) as outfh:
        for entity in path_entities(path, Entity):
            record = senzing_record(dataset, entity)
            if record is None:
                continue
            out = orjson.dumps(record, option=orjson.OPT_APPEND_NEWLINE)
            outfh.write(out)


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
@click.option("-r", "--resolver", required=True, type=ResPath)
def statements_apply(infile: Path, outpath: Path, format: str, resolver: Path) -> None:
    resolver_ = _get_resolver(infile, resolver)

    def _generate() -> Generator[Statement, None, None]:
        for stmt in read_path_statements(
            infile, format=format, statement_type=Statement
        ):
            yield resolver_.apply_statement(stmt)

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
    statements = read_path_statements(
        infile, format=in_format, statement_type=Statement
    )
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
        for stmt in read_path_statements(
            infile, format=format, statement_type=Statement
        ):
            if len(statements) and statements[0].canonical_id != stmt.canonical_id:
                entity = Entity.from_statements(dataset_, statements)
                write_entity(outfh, entity)
                statements = []
            statements.append(stmt)
        if len(statements):
            entity = Entity.from_statements(dataset_, statements)
            write_entity(outfh, entity)


if __name__ == "__main__":
    cli()

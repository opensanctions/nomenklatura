import orjson
import yaml
import click
import logging
import asyncio
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Tuple
from followthemoney.cli.util import path_writer, InPath, OutPath
from followthemoney.cli.util import path_entities, write_entity
from followthemoney.cli.aggregate import sorted_aggregate

from nomenklatura.cache import Cache
from nomenklatura.matching.train import train_matcher
from nomenklatura.loader import FileLoader
from nomenklatura.resolver import Resolver
from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.enrich import Enricher, make_enricher, match, enrich
from nomenklatura.statement import Statement, StatementProxy, CSV, FORMATS
from nomenklatura.statement import write_statements, read_path_statements
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
        dataset = Dataset(data.pop("name"), data.pop("title"))
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
@click.option("--scored/--unscored", is_flag=True, type=click.BOOL, default=True)
def xref_file(
    path: Path,
    resolver: Optional[Path] = None,
    auto_threshold: Optional[float] = None,
    limit: int = 5000,
    scored: bool = True,
) -> None:
    resolver_ = _get_resolver(path, resolver)
    loader = FileLoader(path, resolver=resolver_)
    run_xref(
        loader,
        resolver_,
        auto_threshold=auto_threshold,
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
        for proxy in path_entities(path, Entity):
            proxy = resolver_.apply(proxy)
            if dataset is not None:
                proxy.datasets.add(dataset)
            write_entity(outfh, proxy)


@cli.command("sorted-aggregate", help="Merge sort-order entities")
@click.option("-i", "--infile", type=InPath, default="-")
@click.option("-o", "--outfile", type=OutPath, default="-")
def sorted_aggregate_(infile: Path, outfile: Path) -> None:
    sorted_aggregate(infile, outfile, Entity)


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
    loader = FileLoader(path, resolver=resolver_)
    if xref:
        run_xref(loader, resolver_)

    dedupe_ui(resolver_, loader)
    resolver_.save()


@cli.command("merge-resolver", help="Merge resolver configs")
@click.argument("outpath", type=OutPath)
@click.option("-i", "--inputs", type=InPath, multiple=True)
def merge_resolver(outpath: Path, inputs: Iterable[Path]) -> None:
    resolver = Resolver[Entity].load(outpath)
    for path in inputs:
        resolver.merge(path)
    resolver.save()


@cli.command("train-matcher", help="Train a matching model from judgement pairs")
@click.argument("pairs_file", type=InPath)
def train_matcher_(pairs_file: Path) -> None:
    train_matcher(pairs_file)


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


@cli.command("statements-aggregate", help="Roll up statements into entities")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-f", "--format", type=click.Choice(FORMATS), default=CSV)
def statements_aggregate(path: Path, outpath: Path, format: str) -> None:
    with path_writer(outpath) as outfh:
        statements: List[Statement] = []
        for stmt in read_path_statements(path, format=format, statement_type=Statement):
            if len(statements) and statements[0].canonical_id != stmt.canonical_id:
                entity = StatementProxy.from_statements(statements)
                write_entity(outfh, entity)
                statements = []
            statements.append(stmt)
        if len(statements):
            entity = StatementProxy.from_statements(statements)
            write_entity(outfh, entity)


if __name__ == "__main__":
    cli()

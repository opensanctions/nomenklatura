import orjson
import yaml
import click
import logging
import asyncio
from pathlib import Path
from typing import Optional, Tuple
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
from nomenklatura.senzing import senzing_record
from nomenklatura.xref import xref as run_xref
from nomenklatura.tui import DedupeApp


log = logging.getLogger(__name__)


def _load_enricher(path: Path) -> Tuple[Dataset, Enricher]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
        dataset = Dataset(data.pop("name"), data.pop("title"))
        cache = Cache.make_default(dataset)
        enricher = make_enricher(dataset, cache, data)
        if enricher is None:
            raise TypeError("Could not load enricher")
        return dataset, enricher


def get_resolver() -> Resolver[Entity]:
    return Resolver[Entity].make_default()


@click.group(help="Nomenklatura data integration")
def cli() -> None:
    logging.basicConfig(level=logging.INFO)


@cli.command("xref", help="Generate dedupe candidates")
@click.argument("path", type=InPath)
@click.option("-a", "--auto-threshold", type=click.FLOAT, default=None)
@click.option("-l", "--limit", type=click.INT, default=5000)
@click.option("--scored/--unscored", is_flag=True, type=click.BOOL, default=True)
def xref_file(
    path: Path,
    auto_threshold: Optional[float] = None,
    limit: int = 5000,
    scored: bool = True,
) -> None:
    resolver = get_resolver()
    loader = FileLoader(path, resolver=resolver)
    run_xref(
        loader,
        resolver,
        auto_threshold=auto_threshold,
        scored=scored,
        limit=limit,
    )


@cli.command("prune", help="Remove dedupe candidates")
def xref_prune() -> None:
    resolver = get_resolver()
    resolver.prune()


@cli.command("apply", help="Output merged entities")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
def apply(path: Path, outpath: Path) -> None:
    resolver = get_resolver()
    with path_writer(outpath) as outfh:
        for proxy in path_entities(path, Entity):
            proxy = resolver.apply(proxy)
            write_entity(outfh, proxy)


@cli.command("sorted-aggregate", help="Merge sort-order entities")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
def sorted_aggregate_(path: Path, outpath: Path) -> None:
    sorted_aggregate(path, outpath, Entity)


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
    resolver = get_resolver()
    loader = FileLoader(path, resolver=resolver)
    if xref:
        run_xref(loader, resolver)

    async def run_app() -> None:
        app = DedupeApp(
            loader=loader,
            resolver=resolver,
            title="nomenklatura de-duplication",
        )
        await app.process_messages()

    asyncio.run(run_app())


@cli.command("train-matcher", help="Train a matching model from judgement pairs")
@click.argument("pairs_file", type=InPath)
def train_matcher_(pairs_file: Path) -> None:
    train_matcher(pairs_file)


@cli.command("match", help="Generate matches from an enrichment source")
@click.argument("config", type=InPath)
@click.argument("entities", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
def match_command(config: Path, entities: Path, outpath: Path) -> None:
    resolver = get_resolver()
    _, enricher = _load_enricher(config)
    try:
        with path_writer(outpath) as fh:
            stream = path_entities(entities, Entity)
            for proxy in match(enricher, resolver, stream):
                write_entity(fh, proxy)
    finally:
        enricher.close()


@cli.command("enrich", help="Fetch extra info from an enrichment source")
@click.argument("config", type=InPath)
@click.argument("entities", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")  # noqa
def enrich_command(config: Path, entities: Path, outpath: Path) -> None:
    resolver = get_resolver()
    _, enricher = _load_enricher(config)
    try:
        with path_writer(outpath) as fh:
            stream = path_entities(entities, Entity)
            for proxy in enrich(enricher, resolver, stream):
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


@cli.command("load-resolver", help="Load file-based resolver info to database")
@click.argument("source", type=InPath)
def load_resolver(source: Path) -> None:
    resolver = get_resolver()
    resolver.load(source)


@cli.command("dump-resolver", help="Load file-based resolver info to database")
@click.argument("target", type=OutPath)
def dump_resolver(target: Path) -> None:
    resolver = get_resolver()
    resolver.save(target)


if __name__ == "__main__":
    cli()

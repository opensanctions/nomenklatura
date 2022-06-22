import yaml
import click
import logging
import asyncio
from pathlib import Path
from typing import Iterable, Optional, Tuple
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
from nomenklatura.xref import xref as run_xref
from nomenklatura.tui import DedupeApp


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


@cli.command("apply", help="Output merged entities")
@click.argument("path", type=InPath)
@click.option("-o", "--outpath", type=OutPath, default="-")
@click.option("-r", "--resolver", required=True, type=ResPath)
def apply(path: Path, outpath: Path, resolver: Optional[Path]) -> None:
    resolver_ = _get_resolver(path, resolver)
    with path_writer(outpath) as outfh:
        for proxy in path_entities(path, Entity):
            proxy = resolver_.apply(proxy)
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
@click.option("-r", "--resolver", type=ResPath)
def dedupe(path: Path, xref: bool = False, resolver: Optional[Path] = None) -> None:
    resolver_ = _get_resolver(path, resolver)
    loader = FileLoader(path, resolver=resolver_)
    if xref:
        run_xref(loader, resolver_)

    async def run_app() -> None:
        app = DedupeApp(
            loader=loader,
            resolver=resolver_,
            title="nomenklatura de-duplication",
        )
        await app.process_messages()

    asyncio.run(run_app())
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


if __name__ == "__main__":
    cli()

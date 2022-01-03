import click
import logging
from pathlib import Path
from typing import Optional
from followthemoney.cli.util import write_object

from nomenklatura.index.index import Index
from nomenklatura.loader import FileLoader
from nomenklatura.resolver import Resolver
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.xref import xref
from nomenklatura.tui import DedupeApp
from nomenklatura.util import coro


log = logging.getLogger(__name__)


def _path_sibling(path: Path, suffix: str) -> Path:
    return path.parent.joinpath(f"{path.stem}{suffix}")


async def _get_resolver(
    file_path: Path, resolver_path: Optional[Path]
) -> Resolver[Entity]:
    path = resolver_path or _path_sibling(file_path, ".rslv.ijson")
    return await Resolver[Entity].load(Path(path))


def index_xref(loader: FileLoader, resolver: Resolver[Entity]) -> None:
    index = Index(loader)
    index.build()
    xref(index, resolver, loader._entities.values())


@click.group(help="Nomenklatura data integration")
def cli() -> None:
    logging.basicConfig(level=logging.INFO)


@cli.command("index", help="Index entities from the given file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-i", "--index", type=click.Path(writable=True, path_type=Path))
@coro
async def index(path: Path, index: Optional[Path] = None) -> None:
    loader = await FileLoader.from_file(path)
    index_path = index or _path_sibling(path, ".idx.pkl")
    index_obj = await Index.load(loader, index_path)
    await index_obj.save(index_path)


@cli.command("xref", help="Generate dedupe candidates")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
@coro
async def xref_file(path: Path, resolver: Optional[Path] = None) -> None:
    resolver_ = await _get_resolver(path, resolver)
    loader = await FileLoader.from_file(path, resolver=resolver_)
    index_xref(loader, resolver_)
    await resolver_.save()
    log.info("Xref complete in: %s", resolver_.path)


@cli.command("prune", help="Remove dedupe candidates")
@click.argument("resolver", type=click.Path(exists=True, path_type=Path))
@click.option("-k", "--keep", type=int, default=0)
@coro
async def xref_prune(resolver: Path, keep: int = 0) -> None:
    resolver_ = await _get_resolver(resolver, resolver)
    resolver_.prune(keep=keep)
    await resolver_.save()


@cli.command("apply", help="Output merged entities")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--outfile", type=click.File("w"), default="-")  # noqa
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
@coro
async def apply(path: Path, outfile: click.File, resolver: Optional[Path]) -> None:
    resolver_ = await _get_resolver(path, resolver)
    loader = await FileLoader.from_file(path, resolver=resolver_)
    async for entity in loader.entities():
        write_object(outfile, entity)  # type: ignore


@cli.command("dedupe", help="Interactively judge xref candidates")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-x", "--xref", is_flag=True, default=False)
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
@coro
async def dedupe(
    path: Path, xref: bool = False, resolver: Optional[Path] = None
) -> None:
    resolver_ = await _get_resolver(path, resolver)
    loader = await FileLoader.from_file(path, resolver=resolver_)
    if xref:
        index_xref(loader, resolver_)
    app = DedupeApp(
        loader=loader,
        resolver=resolver_,
        title="NK De-duplication",
        log="textual.log",
    )  # type: ignore
    await app.process_messages()

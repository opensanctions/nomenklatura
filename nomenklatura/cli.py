import click
import logging
import asyncio
from pathlib import Path
from typing import Optional
from followthemoney.cli.util import write_object

from nomenklatura.index.index import Index
from nomenklatura.loader import FileLoader
from nomenklatura.resolver import Resolver
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.xref import xref
from nomenklatura.tui import DedupeApp


log = logging.getLogger(__name__)


def _path_sibling(path: Path, suffix: str) -> Path:
    return path.parent.joinpath(f"{path.stem}{suffix}")


def _get_resolver(file_path: Path, resolver_path: Optional[Path]) -> Resolver[Entity]:
    path = resolver_path or _path_sibling(file_path, ".rslv.ijson")
    return Resolver[Entity].load(Path(path))


def index_xref(loader: FileLoader, resolver: Resolver[Entity]) -> None:
    index = Index(loader)
    index.build()
    xref(index, resolver, loader)


@click.group(help="Nomenklatura data integration")
def cli() -> None:
    logging.basicConfig(level=logging.INFO)


@cli.command("index", help="Index entities from the given file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-i", "--index", type=click.Path(writable=True, path_type=Path))
def index(path: Path, index: Optional[Path] = None) -> None:
    loader = FileLoader(path)
    index_path = index or _path_sibling(path, ".idx.pkl")
    index_obj = Index.load(loader, index_path)
    index_obj.save(index_path)


@cli.command("xref", help="Generate dedupe candidates")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
def xref_file(path: Path, resolver: Optional[Path] = None) -> None:
    resolver_ = _get_resolver(path, resolver)
    loader = FileLoader(path, resolver=resolver_)
    index_xref(loader, resolver_)
    resolver_.save()
    log.info("Xref complete in: %s", resolver_.path)


@cli.command("prune", help="Remove dedupe candidates")
@click.argument("resolver", type=click.Path(exists=True, path_type=Path))
@click.option("-k", "--keep", type=int, default=0)
def xref_prune(resolver: Path, keep: int = 0) -> None:
    resolver_ = _get_resolver(resolver, resolver)
    resolver_.prune(keep=keep)
    resolver_.save()


@cli.command("apply", help="Output merged entities")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--outfile", type=click.File("w"), default="-")  # noqa
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
def apply(path: Path, outfile: click.File, resolver: Optional[Path]) -> None:
    resolver_ = _get_resolver(path, resolver)
    loader = FileLoader(path, resolver=resolver_)
    for entity in loader:
        write_object(outfile, entity)  # type: ignore


@cli.command("dedupe", help="Interactively judge xref candidates")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-x", "--xref", is_flag=True, default=False)
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
def dedupe(path: Path, xref: bool = False, resolver: Optional[Path] = None) -> None:
    resolver_ = _get_resolver(path, resolver)
    loader = FileLoader(path, resolver=resolver_)
    if xref:
        index_xref(loader, resolver_)

    async def run_app() -> None:
        app = DedupeApp(
            loader=loader,
            resolver=resolver_,
            title="NK De-duplication",
            log="textual.log",
        )  # type: ignore
        await app.process_messages()

    asyncio.run(run_app())

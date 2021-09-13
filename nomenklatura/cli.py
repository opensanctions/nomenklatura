import click
import logging
from pathlib import Path

from nomenklatura.index.index import Index
from nomenklatura.loader import FileLoader
from nomenklatura.resolver import Resolver
from nomenklatura.xref import xref
from nomenklatura.tui import DedupeApp


log = logging.getLogger(__name__)


def _path_sibling(path, suffix):
    return path.parent.joinpath(f"{path.stem}{suffix}")


def _get_resolver(file_path, resolver_path):
    path = resolver_path or _path_sibling(file_path, ".rslv.ijson")
    return Resolver.load(Path(path))


@click.group(help="Nomenklatura data integration")
def cli():
    logging.basicConfig(level=logging.INFO)


@cli.command("index", help="Index entities from the given file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-i", "--index", type=click.Path(writable=True, path_type=Path))
def index(path, index=None):
    loader = FileLoader(path)
    index_path = index or _path_sibling(path)
    index = Index.load(loader, index_path)
    index.save()


@cli.command("xref", help="Generate dedupe candidates")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
def xref_file(path, resolver=None):
    loader = FileLoader(path)
    resolver_ = _get_resolver(path, resolver)
    index = Index(loader)
    index.build()
    xref(index, resolver_, loader)
    resolver_.save()
    log.info("Xref complete in: %s", resolver_.path)


# @cli.command("apply", help="Remove dedupe candidates")
# @click.option("-k", "--keep", type=int, default=0)
# def apply(keep=0):
#     resolver = get_resolver()
#     resolver.prune(keep=keep)
#     resolver.save()


@cli.command("dedupe", help="Interactively judge xref candidates")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-r", "--resolver", type=click.Path(writable=True, path_type=Path))
def dedupe(path, resolver):
    loader = FileLoader(path)
    resolver_ = _get_resolver(path, resolver)
    DedupeApp.run(loader=loader, resolver=resolver_)

import sys

from nomenklatura.tui.app import DedupeApp

__all__ = ["DedupeApp"]

# from textual import log
# from textual.reactive import Reactive

if __name__ == "__main__":
    from pathlib import Path
    from nomenklatura.loader import FileLoader
    from nomenklatura.resolver import Resolver
    from nomenklatura.entity import CompositeEntity
    from nomenklatura.index import Index
    from nomenklatura.xref import xref

    resolver = Resolver[CompositeEntity](Path("resolve.ijson"))
    loader = FileLoader(Path(sys.argv[1]))
    index = Index(loader)
    index.build()
    xref(loader, resolver)
    DedupeApp.run(
        title="NK De-duplication", log="textual.log", loader=loader, resolver=resolver
    )

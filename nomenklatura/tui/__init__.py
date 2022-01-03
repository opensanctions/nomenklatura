import sys
import asyncio

from nomenklatura.tui.app import DedupeApp

__all__ = ["DedupeApp"]

# from textual import log
# from textual.reactive import Reactive


async def main():
    from pathlib import Path
    from nomenklatura.loader import FileLoader
    from nomenklatura.resolver import Resolver
    from nomenklatura.index import Index
    from nomenklatura.xref import xref

    resolver = Resolver(Path("resolve.ijson"))
    loader = await FileLoader.from_file(Path(sys.argv[1]))
    index = Index(loader)
    await index.build()
    await xref(index, resolver, list(loader))
    app = DedupeApp(
        loader=loader, resolver=resolver, title="NK De-duplication", log="textual.log"
    )
    await app.process_messages()


if __name__ == "__main__":
    asyncio.run(main())

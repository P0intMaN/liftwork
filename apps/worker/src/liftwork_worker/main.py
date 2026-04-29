"""Worker entrypoint.

Phase 0 ships a no-op worker that proves the import path and exposes a
`WorkerSettings` arq class. Build/deploy job handlers land in Phase 4.
"""

from __future__ import annotations

import asyncio
import sys


async def _noop() -> int:
    return 0


def main() -> int:
    return asyncio.run(_noop())


if __name__ == "__main__":
    sys.exit(main())

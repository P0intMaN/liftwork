"""Worker process entrypoint.

Usage:
    python -m liftwork_worker.main
    # equivalent to:
    arq liftwork_worker.arq_worker.WorkerSettings

The latter is what `make dev-worker` runs.
"""

from __future__ import annotations

import sys

from arq.cli import cli


def main() -> int:
    # Hand off to arq's CLI with our WorkerSettings dotted path.
    sys.argv = [sys.argv[0], "liftwork_worker.arq_worker.WorkerSettings"]
    cli()
    return 0


if __name__ == "__main__":
    sys.exit(main())

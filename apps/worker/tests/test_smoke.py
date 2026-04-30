"""Smoke checks that the worker package + arq settings import cleanly."""

from __future__ import annotations


def test_module_imports() -> None:
    import liftwork_worker  # noqa: F401
    from liftwork_worker.arq_worker import WorkerSettings
    from liftwork_worker.jobs import run_build, run_deploy

    assert WorkerSettings.functions == [run_build, run_deploy]
    assert WorkerSettings.max_jobs > 0
    assert WorkerSettings.job_timeout > 0

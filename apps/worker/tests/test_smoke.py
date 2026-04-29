from liftwork_worker.main import main


def test_noop_main_returns_zero() -> None:
    assert main() == 0

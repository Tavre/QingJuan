import os

from app.process_lifecycle import is_process_running


def test_current_process_is_running() -> None:
    assert is_process_running(os.getpid())


def test_invalid_process_is_not_running() -> None:
    assert not is_process_running(-1)

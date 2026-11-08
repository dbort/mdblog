import os
import time
from collections.abc import Callable, Iterator

import pytest

from check_runner import OFFLINE_ENV


@pytest.fixture
def local_zone() -> Iterator[Callable[[str], None]]:
    """Sets the process's local zone from a POSIX `TZ` string, restoring it afterward."""
    with pytest.MonkeyPatch.context() as patch:

        def set_zone(zone: str) -> None:
            patch.setenv("TZ", zone)
            time.tzset()

        yield set_zone
    time.tzset()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get(OFFLINE_ENV) != "1":
        return
    skip = pytest.mark.skip(
        reason="tools/check --offline skips tests that run wrangler"
    )
    for item in items:
        if item.get_closest_marker("wrangler") is not None:
            item.add_marker(skip)

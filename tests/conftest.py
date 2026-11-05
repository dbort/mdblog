import time
from collections.abc import Callable, Iterator

import pytest


@pytest.fixture
def local_zone() -> Iterator[Callable[[str], None]]:
    """Sets the process's local zone from a POSIX `TZ` string, restoring it afterward."""
    with pytest.MonkeyPatch.context() as patch:

        def set_zone(zone: str) -> None:
            patch.setenv("TZ", zone)
            time.tzset()

        yield set_zone
    time.tzset()

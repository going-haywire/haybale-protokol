"""The repo's haybales load into a library system."""

from typing import Any

import pytest


@pytest.mark.integration
def test_protokol_library_loads(library_system: Any) -> None:
    assert library_system.get_library_registry().is_library_enabled("haybale-protokol")

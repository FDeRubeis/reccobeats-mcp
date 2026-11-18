import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_collection_modifyitems(config, items):
    """Skip e2e tests unless they were explicitly selected with `-m e2e`."""
    markexpr = config.getoption("markexpr") or ""
    if "e2e" in markexpr and "not e2e" not in markexpr:
        return
    skip = pytest.mark.skip(reason="e2e test; run with -m e2e")
    for item in items:
        if item.get_closest_marker("e2e"):
            item.add_marker(skip)

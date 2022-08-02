from typing import Dict, Tuple
import pytest


def pytest_runtest_makereport(item, call):
    if "incremental" in item.keywords and call.excinfo is not None:
        parent = item.parent
        parent._previousfailed = item


def pytest_runtest_setup(item):
    previousfailed = getattr(item.parent, "_previousfailed", None)
    if previousfailed is not None:
        pytest.xfail(f"previous test failed ({previousfailed.name})")

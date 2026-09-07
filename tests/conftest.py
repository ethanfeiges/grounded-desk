from __future__ import annotations

import pytest

from grounded_desk.mock_worker import MockWorker


@pytest.fixture
def canonical() -> MockWorker:
    return MockWorker("canonical")


@pytest.fixture
def decoy() -> MockWorker:
    return MockWorker("decoy")

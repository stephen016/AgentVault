"""Shared test fixtures for AgentVault."""

from __future__ import annotations

import pytest

from agentvault import AsyncVault, Vault


@pytest.fixture(params=["memory", "sqlite"])
def vault(request: pytest.FixtureRequest, tmp_path: object) -> Vault:
    """Parameterized sync vault fixture — runs tests against all backends."""
    if request.param == "memory":
        v = Vault("test", backend="memory")
    else:
        v = Vault("test", backend="sqlite", path=str(tmp_path / "test.db"))  # type: ignore[operator]
    yield v  # type: ignore[misc]
    v.close()


@pytest.fixture(params=["memory", "sqlite"])
async def async_vault(request: pytest.FixtureRequest, tmp_path: object) -> AsyncVault:
    """Parameterized async vault fixture — runs tests against all backends."""
    if request.param == "memory":
        v = await AsyncVault.connect("test", backend="memory")
    else:
        v = await AsyncVault.connect(
            "test", backend="sqlite", path=str(tmp_path / "test.db")  # type: ignore[operator]
        )
    yield v  # type: ignore[misc]
    await v.close()

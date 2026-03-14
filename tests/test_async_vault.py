"""Tests for the async AsyncVault API."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentvault import AsyncVault, ConflictError


class SampleModel(BaseModel):
    name: str
    score: float


@pytest.mark.asyncio
async def test_put_and_get(async_vault: AsyncVault) -> None:
    await async_vault.put("key1", {"hello": "world"}, agent="tester")
    assert await async_vault.get("key1") == {"hello": "world"}


@pytest.mark.asyncio
async def test_get_missing(async_vault: AsyncVault) -> None:
    assert await async_vault.get("nonexistent") is None


@pytest.mark.asyncio
async def test_get_with_default(async_vault: AsyncVault) -> None:
    assert await async_vault.get("missing", default="fallback") == "fallback"


@pytest.mark.asyncio
async def test_get_with_model(async_vault: AsyncVault) -> None:
    await async_vault.put("m", SampleModel(name="x", score=1.0))
    result = await async_vault.get("m", model=SampleModel)
    assert isinstance(result, SampleModel)
    assert result.name == "x"


@pytest.mark.asyncio
async def test_delete(async_vault: AsyncVault) -> None:
    await async_vault.put("key", "val")
    assert await async_vault.delete("key") is True
    assert await async_vault.get("key") is None
    assert await async_vault.delete("key") is False


@pytest.mark.asyncio
async def test_keys(async_vault: AsyncVault) -> None:
    await async_vault.put("a", 1, agent="alice")
    await async_vault.put("b", 2, agent="bob")
    await async_vault.put("c", 3, agent="alice")

    assert sorted(await async_vault.keys()) == ["a", "b", "c"]
    assert sorted(await async_vault.keys(agent="alice")) == ["a", "c"]


@pytest.mark.asyncio
async def test_version_increments(async_vault: AsyncVault) -> None:
    await async_vault.put("k", "v1")
    e1 = await async_vault.get_entry("k")
    assert e1 is not None and e1.version == 1

    await async_vault.put("k", "v2")
    e2 = await async_vault.get_entry("k")
    assert e2 is not None and e2.version == 2


@pytest.mark.asyncio
async def test_cas_success(async_vault: AsyncVault) -> None:
    await async_vault.put("k", "v1")
    await async_vault.put("k", "v2", expected_version=1)
    assert await async_vault.get("k") == "v2"


@pytest.mark.asyncio
async def test_cas_conflict(async_vault: AsyncVault) -> None:
    await async_vault.put("k", "v1")
    with pytest.raises(ConflictError):
        await async_vault.put("k", "v2", expected_version=99)


@pytest.mark.asyncio
async def test_clear(async_vault: AsyncVault) -> None:
    await async_vault.put("a", 1)
    await async_vault.put("b", 2)
    count = await async_vault.clear()
    assert count == 2
    assert await async_vault.keys() == []


@pytest.mark.asyncio
async def test_context_manager() -> None:
    async with await AsyncVault.connect("test", backend="memory") as v:
        await v.put("k", "v")
        assert await v.get("k") == "v"

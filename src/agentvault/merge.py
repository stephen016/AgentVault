"""Semantic Conflict Resolution — pluggable merge strategies for concurrent writes.

Instead of binary CAS (match or error), agents can define merge strategies.
When two agents write to the same key and a conflict occurs, the merge
strategy resolves it automatically.

Built-in strategies:
- last_write_wins: Default. Latest write overwrites (no merge).
- list_append: Both values are lists — concatenate and deduplicate.
- dict_deep_merge: Both values are dicts — recursively merge.
- custom: User-provided merge function.
"""

from __future__ import annotations

from typing import Any, Protocol


class MergeFunction(Protocol):
    """Protocol for merge functions."""

    def __call__(self, key: str, old_value: Any, new_value: Any) -> Any:
        """Merge old and new values for a key.

        Args:
            key: The key being written.
            old_value: The current value in the vault.
            new_value: The value the agent is trying to write.

        Returns:
            The merged result to store.
        """
        ...


def last_write_wins(key: str, old_value: Any, new_value: Any) -> Any:
    """Default strategy: new value overwrites old."""
    return new_value


def list_append(key: str, old_value: Any, new_value: Any) -> Any:
    """Merge two lists by concatenation with deduplication.

    If values aren't lists, falls back to last-write-wins.
    Items are deduplicated while preserving order.
    """
    if not isinstance(old_value, list) or not isinstance(new_value, list):
        return new_value

    seen = set()
    merged = []
    for item in old_value + new_value:
        # Use repr for unhashable types
        try:
            item_key = item if isinstance(item, (str, int, float, bool)) else repr(item)
        except Exception:
            item_key = id(item)

        if item_key not in seen:
            seen.add(item_key)
            merged.append(item)

    return merged


def dict_deep_merge(key: str, old_value: Any, new_value: Any) -> Any:
    """Recursively merge two dicts. New values take precedence for conflicts.

    If values aren't dicts, falls back to last-write-wins.
    """
    if not isinstance(old_value, dict) or not isinstance(new_value, dict):
        return new_value

    return _deep_merge(old_value, new_value)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on leaf conflicts."""
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        elif (
            key in result
            and isinstance(result[key], list)
            and isinstance(value, list)
        ):
            # Merge lists within dicts too
            result[key] = list_append(key, result[key], value)
        else:
            result[key] = value
    return result


class MergeRegistry:
    """Registry of merge strategies for vault keys.

    Allows setting per-key or default merge strategies that are applied
    when a ConflictError would normally be raised.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, MergeFunction] = {}
        self._default: MergeFunction | None = None

    def set_strategy(
        self,
        key: str | None,
        strategy: MergeFunction | str,
    ) -> None:
        """Set a merge strategy for a specific key or as default.

        Args:
            key: The key to set strategy for. None sets the default.
            strategy: A merge function or built-in name
                      ("last_write_wins", "list_append", "dict_deep_merge").
        """
        fn = _resolve_strategy(strategy)
        if key is None:
            self._default = fn
        else:
            self._strategies[key] = fn

    def get_strategy(self, key: str) -> MergeFunction | None:
        """Get the merge strategy for a key, or the default."""
        return self._strategies.get(key, self._default)

    def has_strategy(self, key: str) -> bool:
        """Check if a merge strategy is registered for a key (or default)."""
        return key in self._strategies or self._default is not None

    def clear(self) -> None:
        """Remove all registered strategies."""
        self._strategies.clear()
        self._default = None


_BUILTIN_STRATEGIES: dict[str, MergeFunction] = {
    "last_write_wins": last_write_wins,
    "list_append": list_append,
    "dict_deep_merge": dict_deep_merge,
}


def _resolve_strategy(strategy: MergeFunction | str) -> MergeFunction:
    """Resolve a strategy name or function to a MergeFunction."""
    if isinstance(strategy, str):
        if strategy not in _BUILTIN_STRATEGIES:
            raise ValueError(
                f"Unknown merge strategy: '{strategy}'. "
                f"Available: {list(_BUILTIN_STRATEGIES.keys())}"
            )
        return _BUILTIN_STRATEGIES[strategy]
    return strategy

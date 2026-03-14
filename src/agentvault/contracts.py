"""Agent Contracts — typed declarations of what each agent produces and consumes."""

from __future__ import annotations

import logging
from typing import Any, Literal, get_args, get_origin

from agentvault.exceptions import ContractViolationError
from agentvault.types import AgentContract

logger = logging.getLogger(__name__)

EnforcementMode = Literal["strict", "warn", "off"]


def _check_type(value: Any, expected: Any) -> bool:
    """Check if value matches expected type, including generics like list[str].

    Returns True if the value matches, False otherwise.
    """
    if expected is Any:
        return True

    origin = get_origin(expected)

    if origin is None:
        # Plain type like str, int, dict
        return isinstance(value, expected)

    # Generic type like list[str], dict[str, int]
    if not isinstance(value, origin):
        return False

    type_args = get_args(expected)
    if not type_args:
        return True

    # Validate inner types
    if origin is list:
        inner = type_args[0]
        return all(_check_type(item, inner) for item in value)
    elif origin is dict:
        key_type, val_type = type_args
        return all(
            _check_type(k, key_type) and _check_type(v, val_type)
            for k, v in value.items()
        )
    elif origin is set:
        inner = type_args[0]
        return all(_check_type(item, inner) for item in value)
    elif origin is tuple:
        if len(type_args) == 2 and type_args[1] is Ellipsis:
            return all(_check_type(item, type_args[0]) for item in value)
        if len(value) != len(type_args):
            return False
        return all(_check_type(v, t) for v, t in zip(value, type_args))

    # For other generic types, just check the origin
    return True


def _type_name(t: Any) -> str:
    """Get a readable name for a type, including generics."""
    origin = get_origin(t)
    if origin is None:
        return getattr(t, "__name__", str(t))
    args = get_args(t)
    if args:
        arg_names = ", ".join(_type_name(a) for a in args if a is not Ellipsis)
        return f"{origin.__name__}[{arg_names}]"
    return origin.__name__


class ContractRegistry:
    """Registry of agent contracts with runtime validation."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentContract] = {}
        self._enforcement: EnforcementMode = "off"

    @property
    def enforcement(self) -> EnforcementMode:
        return self._enforcement

    @enforcement.setter
    def enforcement(self, mode: EnforcementMode) -> None:
        self._enforcement = mode

    def register(self, contract: AgentContract) -> None:
        """Register an agent contract. Raises ValueError if name already registered."""
        if contract.name in self._agents:
            raise ValueError(
                f"Agent '{contract.name}' is already registered"
            )
        self._agents[contract.name] = contract

    def unregister(self, name: str) -> bool:
        """Unregister an agent contract. Returns True if it existed."""
        if name in self._agents:
            del self._agents[name]
            return True
        return False

    def validate_put(self, agent: str | None, key: str, value: Any) -> None:
        """Validate a put operation against registered contracts.

        Called from AsyncVault.put() before serialization.
        """
        if self._enforcement == "off":
            return
        if agent is None:
            return
        if agent not in self._agents:
            return

        contract = self._agents[agent]

        # Check key is in agent's produces
        if key not in contract.produces:
            self._handle_violation(agent, key, f"key '{key}' not in declared produces")
            return

        # Check type matches (supports generics like list[str])
        expected_type = contract.produces[key]
        if not _check_type(value, expected_type):
            self._handle_violation(
                agent, key,
                f"expected type {_type_name(expected_type)}, "
                f"got {type(value).__name__}"
            )

    def _handle_violation(self, agent: str, key: str, reason: str) -> None:
        if self._enforcement == "strict":
            raise ContractViolationError(agent, key, reason)
        elif self._enforcement == "warn":
            logger.warning(f"Contract violation by '{agent}' on key '{key}': {reason}")

    def get_dependency_graph(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return a dependency graph of all registered agents."""
        graph: dict[str, dict[str, dict[str, Any]]] = {}
        for name, contract in self._agents.items():
            graph[name] = {
                "produces": dict(contract.produces),
                "consumes": dict(contract.consumes),
                "description": contract.description,
            }
        return graph

    def validate_contracts(self) -> list[str]:
        """Check for structural issues across all registered contracts.

        Returns a list of issue descriptions.
        """
        issues: list[str] = []

        # Build maps of producers and consumers
        producers: dict[str, list[tuple[str, Any]]] = {}  # key -> [(agent, type)]
        consumers: dict[str, list[tuple[str, Any]]] = {}  # key -> [(agent, type)]

        for name, contract in self._agents.items():
            for key, typ in contract.produces.items():
                producers.setdefault(key, []).append((name, typ))
            for key, typ in contract.consumes.items():
                consumers.setdefault(key, []).append((name, typ))

        # Check consumed keys with no producer
        for key, consumer_list in consumers.items():
            if key not in producers:
                agent_names = ", ".join(f"'{a}'" for a, _ in consumer_list)
                issues.append(
                    f"Key '{key}' consumed by {agent_names} but no agent produces it"
                )

        # Check multiple agents producing same key
        for key, producer_list in producers.items():
            if len(producer_list) > 1:
                agent_names = ", ".join(f"'{a}'" for a, _ in producer_list)
                issues.append(
                    f"Key '{key}' produced by multiple agents: {agent_names}"
                )

        # Check type mismatches between producer and consumer
        for key in consumers:
            if key in producers:
                for prod_agent, prod_type in producers[key]:
                    for cons_agent, cons_type in consumers[key]:
                        if (
                            prod_type is not Any
                            and cons_type is not Any
                            and prod_type != cons_type
                        ):
                            issues.append(
                                f"Type mismatch on key '{key}': "
                                f"'{prod_agent}' produces {_type_name(prod_type)}, "
                                f"'{cons_agent}' consumes {_type_name(cons_type)}"
                            )

        return issues

"""CLI inspector for AgentVault — view and inspect vault contents."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def main() -> None:
    """Entry point for the agentvault CLI."""
    parser = argparse.ArgumentParser(
        prog="agentvault",
        description="AgentVault — Shared memory and state coordination for AI agents",
    )
    subparsers = parser.add_subparsers(dest="command")

    # inspect subcommand
    inspect_parser = subparsers.add_parser("inspect", help="Inspect vault contents")
    inspect_parser.add_argument("name", nargs="?", default="default", help="Vault name")
    inspect_parser.add_argument("--key", help="Show details for a specific key")
    inspect_parser.add_argument("--history", action="store_true", help="Show version history")
    inspect_parser.add_argument("--agent", help="Filter by agent")
    inspect_parser.add_argument("--path", help="Custom database path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "inspect":
        _inspect(args)


def _inspect(args: argparse.Namespace) -> None:
    """Inspect vault contents."""
    from agentvault import Vault

    vault = Vault(args.name, path=args.path)
    try:
        if args.key and args.history:
            _show_history(vault, args.key)
        elif args.key:
            _show_entry(vault, args.key)
        else:
            _show_entries(vault, agent=args.agent)
    finally:
        vault.close()


def _show_entries(vault: Any, agent: str | None = None) -> None:
    """Show all entries in a table format."""
    keys = vault.keys(agent=agent)
    if not keys:
        print("(vault is empty)")
        return

    # Header
    print(f"{'KEY':<30} {'AGENT':<15} {'VERSION':<8} {'UPDATED':<25} {'VALUE PREVIEW'}")
    print("-" * 100)

    for key in keys:
        entry = vault.get_entry(key)
        if entry is None:
            continue
        value_preview = _preview(entry.value, max_len=40)
        agent_str = entry.agent or "-"
        updated = entry.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{key:<30} {agent_str:<15} {entry.version:<8} {updated:<25} {value_preview}")


def _show_entry(vault: Any, key: str) -> None:
    """Show details for a specific entry."""
    entry = vault.get_entry(key)
    if entry is None:
        print(f"Key '{key}' not found")
        sys.exit(1)

    print(f"Key:       {entry.key}")
    print(f"Agent:     {entry.agent or '-'}")
    print(f"Version:   {entry.version}")
    print(f"Created:   {entry.created_at.isoformat()}")
    print(f"Updated:   {entry.updated_at.isoformat()}")
    if entry.metadata:
        print(f"Metadata:  {json.dumps(entry.metadata, indent=2)}")
    print("Value:")
    print(json.dumps(entry.value, indent=2, default=str))


def _show_history(vault: Any, key: str) -> None:
    """Show version history for a key."""
    entries = vault.history(key)
    if not entries:
        print(f"No history for key '{key}'")
        return

    print(f"History for '{key}' ({len(entries)} versions):")
    print(f"{'VERSION':<10} {'AGENT':<15} {'TIMESTAMP':<25} {'VALUE PREVIEW'}")
    print("-" * 80)

    for entry in entries:
        value_preview = _preview(entry.value, max_len=40)
        agent_str = entry.agent or "-"
        ts = entry.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{entry.version:<10} {agent_str:<15} {ts:<25} {value_preview}")


def _preview(value: object, max_len: int = 40) -> str:
    """Create a short preview of a value."""
    s = json.dumps(value, default=str)
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


if __name__ == "__main__":
    main()

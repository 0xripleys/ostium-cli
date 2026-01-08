"""Utility functions for Ostium CLI."""

import asyncio
from typing import Any

from eth_account import Account
from ostium_python_sdk import NetworkConfig, OstiumSDK
from rich.console import Console
from rich.table import Table

from ostium_cli.config import Network, get_private_key, get_rpc_url

console = Console()


def get_sdk(network: Network, require_key: bool = True) -> OstiumSDK:
    """Initialize and return the Ostium SDK."""
    private_key = get_private_key() if require_key else None
    rpc_url = get_rpc_url(network)

    if network == Network.mainnet:
        config = NetworkConfig.mainnet()
    else:
        config = NetworkConfig.testnet()

    return OstiumSDK(config, private_key, rpc_url)


def get_address() -> str:
    """Get wallet address from private key."""
    private_key = get_private_key()
    account = Account.from_key(private_key)
    return account.address


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def create_table(title: str, columns: list[tuple[str, str]]) -> Table:
    """Create a Rich table with the given columns."""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    for name, style in columns:
        table.add_column(name, style=style)
    return table


def format_direction(is_long: bool) -> str:
    """Format trade direction with color."""
    if is_long:
        return "[green]LONG[/green]"
    return "[red]SHORT[/red]"


def format_pnl(pnl: float) -> str:
    """Format PnL with color."""
    if pnl >= 0:
        return f"[green]+${pnl:.2f}[/green]"
    return f"[red]-${abs(pnl):.2f}[/red]"

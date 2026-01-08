"""Command to list open orders."""

import json
from typing import Optional

import typer

from ostium_cli.config import Network
from ostium_cli.utils import (
    console,
    create_table,
    format_direction,
    get_address,
    get_sdk,
    run_async,
)

app = typer.Typer()


async def fetch_orders(network: Network, address: Optional[str] = None, output_json: bool = False) -> None:
    """Fetch and display open orders."""
    # Use provided address or derive from private key
    if address is None:
        address = get_address()

    sdk = get_sdk(network, require_key=False)

    if not output_json:
        console.print(f"Fetching orders for [cyan]{address}[/cyan] on [yellow]{network.value}[/yellow]...")

    open_orders = await sdk.subgraph.get_orders(address)

    # JSON output mode - print raw SDK response
    if output_json:
        print(json.dumps(open_orders, indent=2))
        return

    if not open_orders:
        console.print("[yellow]No open orders found.[/yellow]")
        return

    table = create_table(
        f"Open Orders ({len(open_orders)})",
        [
            ("Order ID", "dim"),
            ("Pair", "cyan"),
            ("Type", ""),
            ("Direction", ""),
            ("Collateral", ""),
            ("Leverage", ""),
            ("Trigger Price", "yellow"),
            ("TP", "green"),
            ("SL", "red"),
        ],
    )

    for order in open_orders:
        order_id = order.get("id", "")
        pair_name = order.get("pair", {}).get("from", "???") + "/" + order.get("pair", {}).get("to", "???")

        # Order type from limitType field
        order_type = order.get("limitType", "LIMIT")

        is_long = order.get("isBuy", True)
        # Collateral is in micro-USDC (6 decimals)
        collateral = float(order.get("collateral", 0)) / 1e6
        # Leverage is scaled by 100
        leverage = float(order.get("leverage", 0)) / 100
        # Prices are scaled by 1e18
        trigger_price = float(order.get("openPrice", 0)) / 1e18
        tp_price = float(order.get("takeProfitPrice", 0)) / 1e18
        sl_price = float(order.get("stopLossPrice", 0)) / 1e18

        table.add_row(
            str(order_id),
            pair_name,
            order_type,
            format_direction(is_long),
            f"${collateral:,.2f}",
            f"{leverage:.1f}x",
            f"{trigger_price:,.2f}" if trigger_price else "N/A",
            f"{tp_price:,.2f}" if tp_price else "-",
            f"{sl_price:,.2f}" if sl_price else "-",
        )

    console.print(table)


@app.command()
def orders(
    address: Optional[str] = typer.Option(None, "--address", "-a", help="Wallet address to query (defaults to PRIVATE_KEY)"),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output raw SDK response as JSON"),
) -> None:
    """List open limit/stop orders."""
    run_async(fetch_orders(network, address, output_json))

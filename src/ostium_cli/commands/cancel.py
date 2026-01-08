"""Command to cancel an open limit order."""

import json
from typing import Optional

import typer

from ostium_cli.config import Network
from ostium_cli.utils import (
    console,
    get_address,
    get_sdk,
    run_async,
)

app = typer.Typer()


async def lookup_order_by_id(sdk, address: str, order_id: str) -> Optional[dict]:
    """Look up an order by its ID and return pair_index and order_index."""
    open_orders = await sdk.subgraph.get_orders(address)
    for order in open_orders:
        if order.get("id") == order_id:
            return {
                "pair_index": int(order["pair"]["id"]),
                "order_index": int(order_id.split("_")[-1]),  # Extract index from ID like "0x..._0_0"
                "pair_name": order["pair"].get("from", "???") + "/" + order["pair"].get("to", "???"),
            }
    return None


async def cancel_order(
    network: Network,
    pair_index: Optional[int] = None,
    order_index: Optional[int] = None,
    order_id: Optional[str] = None,
    output_json: bool = False,
) -> None:
    """Cancel an open limit order."""
    sdk = get_sdk(network, require_key=True)

    # If order_id is provided, look up pair_index and order_index
    if order_id is not None:
        address = get_address()
        order_info = await lookup_order_by_id(sdk, address, order_id)
        if order_info is None:
            if output_json:
                print(json.dumps({
                    "success": False,
                    "error": f"Order ID '{order_id}' not found in open orders",
                }, indent=2))
            else:
                console.print(f"[red]Error: Order ID '{order_id}' not found in open orders.[/red]")
            return
        pair_index = order_info["pair_index"]
        order_index = order_info["order_index"]
        if not output_json:
            console.print(f"Found order: [cyan]{order_info['pair_name']}[/cyan] (pair: {pair_index}, index: {order_index})")

    if not output_json:
        console.print(f"Canceling order on [cyan]{network.value}[/cyan]...")
        console.print(f"  Pair Index: [cyan]{pair_index}[/cyan]")
        console.print(f"  Order Index: [cyan]{order_index}[/cyan]")
        console.print("\nSubmitting transaction...")

    try:
        result = sdk.ostium.cancel_limit_order(pair_index, order_index)

        # Handle different return formats from SDK
        tx_hash = None

        if isinstance(result, dict):
            if "transactionHash" in result:
                tx_hash = result["transactionHash"]
            elif "hash" in result:
                tx_hash = result["hash"]
        elif hasattr(result, "transactionHash"):
            tx_hash = result.transactionHash
        elif hasattr(result, "hash"):
            tx_hash = result.hash

        # Convert HexBytes to string
        if tx_hash is not None:
            if hasattr(tx_hash, "hex"):
                tx_hash = tx_hash.hex()
            elif isinstance(tx_hash, bytes):
                tx_hash = tx_hash.hex()

        if output_json:
            print(json.dumps({
                "success": True,
                "transaction_hash": tx_hash,
                "params": {
                    "pair_index": pair_index,
                    "order_index": order_index,
                },
            }, indent=2))
        else:
            console.print(f"\n[green]Order canceled successfully![/green]")
            if tx_hash:
                console.print(f"Transaction hash: [cyan]{tx_hash}[/cyan]")
            else:
                console.print(f"[dim]Result: {result}[/dim]")

    except Exception as e:
        if output_json:
            print(json.dumps({
                "success": False,
                "error": str(e),
            }, indent=2))
        else:
            console.print(f"\n[red]Failed to cancel order: {e}[/red]")


@app.command()
def cancel(
    order_id: Optional[str] = typer.Option(None, "--order-id", "-i", help="Order ID (from orders command)"),
    pair_index: Optional[int] = typer.Option(None, "--pair-index", "-p", help="Pair index of the order"),
    order_index: Optional[int] = typer.Option(None, "--order-index", "-o", help="Order index"),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output result as JSON"),
) -> None:
    """Cancel an open limit order.

    Use either --order-id or both --pair-index and --order-index to identify the order.
    """
    # Validate that either order_id or both pair_index and order_index are provided
    if order_id is None and (pair_index is None or order_index is None):
        console.print("[red]Error: Provide either --order-id or both --pair-index and --order-index[/red]")
        raise typer.Exit(1)

    run_async(cancel_order(network, pair_index, order_index, order_id, output_json))

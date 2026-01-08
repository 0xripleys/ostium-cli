"""Command to close an open trade at market price."""

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


async def lookup_trade_by_id(sdk, address: str, trade_id: str) -> Optional[dict]:
    """Look up a trade by its trade ID and return pair_index and trade_index."""
    open_trades = await sdk.subgraph.get_open_trades(address)
    for trade in open_trades:
        if trade.get("tradeID") == trade_id:
            return {
                "pair_index": int(trade["pair"]["id"]),
                "trade_index": int(trade["index"]),
                "pair_name": trade["pair"].get("from", "???") + "/" + trade["pair"].get("to", "???"),
                "pair_from": trade["pair"].get("from", ""),
                "pair_to": trade["pair"].get("to", "USD"),
                "is_long": trade.get("isBuy", True),
                "collateral": float(trade.get("collateral", 0)) / 1e6,
            }
    return None


async def close_trade(
    network: Network,
    pair_index: Optional[int] = None,
    trade_index: Optional[int] = None,
    trade_id: Optional[str] = None,
    output_json: bool = False,
) -> None:
    """Close an open trade at market price."""
    sdk = get_sdk(network, require_key=True)

    trade_info = None

    # If trade_id is provided, look up pair_index and trade_index
    if trade_id is not None:
        address = get_address()
        trade_info = await lookup_trade_by_id(sdk, address, trade_id)
        if trade_info is None:
            if output_json:
                print(json.dumps({
                    "success": False,
                    "error": f"Trade ID '{trade_id}' not found in open trades",
                }, indent=2))
            else:
                console.print(f"[red]Error: Trade ID '{trade_id}' not found in open trades.[/red]")
            return
        pair_index = trade_info["pair_index"]
        trade_index = trade_info["trade_index"]

    # Get current market price for the asset
    if trade_info:
        pair_from = trade_info["pair_from"]
        pair_to = trade_info["pair_to"]
    else:
        # If we don't have trade_info, we need to look it up
        address = get_address()
        open_trades = await sdk.subgraph.get_open_trades(address)
        for trade in open_trades:
            if int(trade["pair"]["id"]) == pair_index and int(trade["index"]) == trade_index:
                pair_from = trade["pair"].get("from", "")
                pair_to = trade["pair"].get("to", "USD")
                break
        else:
            if output_json:
                print(json.dumps({
                    "success": False,
                    "error": "Could not find trade to get asset info",
                }, indent=2))
            else:
                console.print("[red]Error: Could not find trade to get asset info.[/red]")
            return

    try:
        market_price, _, _ = await sdk.price.get_price(pair_from, pair_to)
    except Exception as e:
        if output_json:
            print(json.dumps({
                "success": False,
                "error": f"Failed to fetch market price: {e}",
            }, indent=2))
        else:
            console.print(f"[red]Error fetching market price: {e}[/red]")
        return

    if not output_json:
        if trade_info:
            direction = "LONG" if trade_info["is_long"] else "SHORT"
            console.print(f"Closing trade: [cyan]{trade_info['pair_name']}[/cyan] {direction} (${trade_info['collateral']:,.2f})")
        console.print(f"Closing trade on [cyan]{network.value}[/cyan]...")
        console.print(f"  Pair Index: [cyan]{pair_index}[/cyan]")
        console.print(f"  Trade Index: [cyan]{trade_index}[/cyan]")
        console.print(f"  Market Price: [cyan]{market_price:,.2f}[/cyan]")
        console.print("\nSubmitting transaction...")

    try:
        result = sdk.ostium.close_trade(pair_index, trade_index, market_price)

        # Handle different return formats from SDK
        # SDK returns {'receipt': AttributeDict(...), 'order_id': ...}
        tx_hash = None

        if isinstance(result, dict):
            # Check for nested receipt object
            if "receipt" in result:
                receipt = result["receipt"]
                if hasattr(receipt, "transactionHash"):
                    tx_hash = receipt.transactionHash
                elif isinstance(receipt, dict) and "transactionHash" in receipt:
                    tx_hash = receipt["transactionHash"]
            elif "transactionHash" in result:
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
                    "trade_id": trade_id,
                    "pair_index": pair_index,
                    "trade_index": trade_index,
                },
            }, indent=2))
        else:
            console.print(f"\n[green]Trade closed successfully![/green]")
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
            console.print(f"\n[red]Failed to close trade: {e}[/red]")


@app.command()
def close(
    trade_id: Optional[str] = typer.Option(None, "--trade-id", "-i", help="Trade ID (from trades command)"),
    pair_index: Optional[int] = typer.Option(None, "--pair-index", "-p", help="Pair index of the trade"),
    trade_index: Optional[int] = typer.Option(None, "--trade-index", "-t", help="Trade index"),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output result as JSON"),
) -> None:
    """Close an open trade at market price.

    Use either --trade-id or both --pair-index and --trade-index to identify the trade.
    """
    # Validate that either trade_id or both pair_index and trade_index are provided
    if trade_id is None and (pair_index is None or trade_index is None):
        console.print("[red]Error: Provide either --trade-id or both --pair-index and --trade-index[/red]")
        raise typer.Exit(1)

    run_async(close_trade(network, pair_index, trade_index, trade_id, output_json))

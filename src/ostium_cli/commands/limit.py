"""Command to create a limit order."""

import json
from typing import Optional

import typer

from ostium_cli.config import Network
from ostium_cli.utils import (
    console,
    get_sdk,
    run_async,
)

app = typer.Typer()


async def get_pair_index(sdk, asset: str) -> Optional[int]:
    """Get the pair index for an asset symbol."""
    pairs = await sdk.subgraph.get_pairs()
    asset_upper = asset.upper()
    for pair in pairs:
        if pair.get("from", "").upper() == asset_upper:
            return int(pair.get("id", -1))
    return None


async def create_limit_order(
    network: Network,
    asset: str,
    direction: str,
    collateral: float,
    leverage: float,
    price: float,
    output_json: bool = False,
) -> None:
    """Create a limit order."""
    sdk = get_sdk(network, require_key=True)

    # Get pair index for the asset
    pair_index = await get_pair_index(sdk, asset)
    if pair_index is None:
        console.print(f"[red]Error: Asset '{asset}' not found. Use a valid asset symbol (e.g., BTC, ETH, XAU).[/red]")
        return

    # Parse direction
    is_long = direction.lower() in ("long", "buy", "l")

    if not output_json:
        console.print(f"Creating [yellow]LIMIT[/yellow] order on [cyan]{network.value}[/cyan]...")
        console.print(f"  Asset: [cyan]{asset.upper()}[/cyan] (pair index: {pair_index})")
        console.print(f"  Direction: [{'green' if is_long else 'red'}]{'LONG' if is_long else 'SHORT'}[/{'green' if is_long else 'red'}]")
        console.print(f"  Collateral: [yellow]${collateral:,.2f}[/yellow]")
        console.print(f"  Leverage: [yellow]{leverage}x[/yellow]")
        console.print(f"  Trigger Price: [cyan]{price:,.2f}[/cyan]")

    # Get current price for reference
    try:
        current_price, _, _ = await sdk.price.get_price(asset.upper(), "USD")
        if not output_json:
            console.print(f"  Current Price: [dim]{current_price:,.2f}[/dim]")
    except Exception:
        current_price = None

    # Build order params
    order_params = {
        "collateral": collateral,
        "leverage": leverage,
        "asset_type": pair_index,
        "direction": is_long,
        "order_type": "LIMIT",
    }

    if not output_json:
        console.print("\nSubmitting order...")

    try:
        result = sdk.ostium.perform_trade(order_params, at_price=price)

        # Handle different return formats from SDK
        # SDK returns {'receipt': AttributeDict(...), 'order_id': ...}
        tx_hash = None
        order_id = None

        if isinstance(result, dict):
            # Check for nested receipt object
            if "receipt" in result:
                receipt = result["receipt"]
                order_id = result.get("order_id")
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
                    "asset": asset.upper(),
                    "pair_index": pair_index,
                    "direction": "long" if is_long else "short",
                    "collateral": collateral,
                    "leverage": leverage,
                    "trigger_price": price,
                    "current_price": current_price,
                },
            }, indent=2))
        else:
            console.print(f"\n[green]Limit order submitted successfully![/green]")
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
            console.print(f"\n[red]Order failed: {e}[/red]")


@app.command()
def limit(
    asset: str = typer.Option(..., "--asset", "-a", help="Asset symbol (e.g., BTC, ETH, XAU)"),
    direction: str = typer.Option(..., "--direction", "-d", help="Trade direction (long/short)"),
    collateral: float = typer.Option(..., "--collateral", "-c", help="Collateral amount in USDC"),
    leverage: float = typer.Option(..., "--leverage", "-l", help="Leverage multiplier (e.g., 10 for 10x)"),
    price: float = typer.Option(..., "--price", "-p", help="Trigger price for the limit order"),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output result as JSON"),
) -> None:
    """Create a limit order at a specific price."""
    run_async(create_limit_order(network, asset, direction, collateral, leverage, price, output_json))

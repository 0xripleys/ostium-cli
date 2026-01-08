"""Command to create a market order."""

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


async def create_market_order(
    network: Network,
    asset: str,
    direction: str,
    collateral: float,
    leverage: float,
    output_json: bool = False,
) -> None:
    """Create a market order."""
    sdk = get_sdk(network, require_key=True)

    # Get pair index for the asset
    pair_index = await get_pair_index(sdk, asset)
    if pair_index is None:
        console.print(f"[red]Error: Asset '{asset}' not found. Use a valid asset symbol (e.g., BTC, ETH, XAU).[/red]")
        return

    # Parse direction
    is_long = direction.lower() in ("long", "buy", "l")

    if not output_json:
        console.print(f"Creating [yellow]MARKET[/yellow] order on [cyan]{network.value}[/cyan]...")
        console.print(f"  Asset: [cyan]{asset.upper()}[/cyan] (pair index: {pair_index})")
        console.print(f"  Direction: [{'green' if is_long else 'red'}]{'LONG' if is_long else 'SHORT'}[/{'green' if is_long else 'red'}]")
        console.print(f"  Collateral: [yellow]${collateral:,.2f}[/yellow]")
        console.print(f"  Leverage: [yellow]{leverage}x[/yellow]")

    # Get latest price
    try:
        latest_price, _, _ = await sdk.price.get_price(asset.upper(), "USD")
        if not output_json:
            console.print(f"  Current Price: [cyan]{latest_price:,.2f}[/cyan]")
    except Exception as e:
        console.print(f"[red]Error fetching price: {e}[/red]")
        return

    # Build trade params
    # Note: leverage in SDK is actual multiplier (not scaled by 100 for input)
    trade_params = {
        "collateral": collateral,
        "leverage": leverage,
        "asset_type": pair_index,
        "direction": is_long,
        "order_type": "MARKET",
    }

    if not output_json:
        console.print("\nSubmitting order...")

    try:
        result = sdk.ostium.perform_trade(trade_params, at_price=latest_price)

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
                    "price": latest_price,
                },
            }, indent=2))
        else:
            console.print(f"\n[green]Order submitted successfully![/green]")
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
def market(
    asset: str = typer.Option(..., "--asset", "-a", help="Asset symbol (e.g., BTC, ETH, XAU)"),
    direction: str = typer.Option(..., "--direction", "-d", help="Trade direction (long/short)"),
    collateral: float = typer.Option(..., "--collateral", "-c", help="Collateral amount in USDC"),
    leverage: float = typer.Option(..., "--leverage", "-l", help="Leverage multiplier (e.g., 10 for 10x)"),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output result as JSON"),
) -> None:
    """Create a market order."""
    run_async(create_market_order(network, asset, direction, collateral, leverage, output_json))

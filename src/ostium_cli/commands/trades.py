"""Command to list open trades with PnL."""

import json
from typing import Optional

import typer

from ostium_cli.config import Network
from ostium_cli.utils import (
    console,
    create_table,
    format_direction,
    format_pnl,
    get_address,
    get_sdk,
    run_async,
)

app = typer.Typer()


async def fetch_trades(network: Network, address: Optional[str] = None, output_json: bool = False) -> None:
    """Fetch and display open trades."""
    # Use provided address or derive from private key
    if address is None:
        address = get_address()

    sdk = get_sdk(network, require_key=False)

    if not output_json:
        console.print(f"Fetching trades for [cyan]{address}[/cyan] on [yellow]{network.value}[/yellow]...")

    open_trades = await sdk.subgraph.get_open_trades(address)

    # JSON output mode - print raw SDK response
    if output_json:
        print(json.dumps(open_trades, indent=2))
        return

    if not open_trades:
        console.print("[yellow]No open trades found.[/yellow]")
        return

    table = create_table(
        f"Open Trades ({len(open_trades)})",
        [
            ("Trade ID", "dim"),
            ("Pair", "cyan"),
            ("Direction", ""),
            ("Collateral", ""),
            ("Leverage", ""),
            ("Entry Price", ""),
            ("Current Price", ""),
            ("Liq Price", "red"),
            ("TP", "green"),
            ("SL", "red"),
            ("PnL", ""),
        ],
    )

    for trade in open_trades:
        trade_id = trade.get("tradeID", "")
        pair_id = trade["pair"]["id"]
        trade_index = trade["index"]
        pair_name = trade["pair"].get("from", "???") + "/" + trade["pair"].get("to", "???")
        is_long = trade.get("isBuy", True)
        # Collateral is in micro-USDC (6 decimals)
        collateral = float(trade.get("collateral", 0)) / 1e6
        # Leverage is scaled by 100 (e.g., 850 = 8.5x)
        leverage = float(trade.get("leverage", 0)) / 100
        # Open price is scaled by 1e18
        open_price = float(trade.get("openPrice", 0)) / 1e18
        # TP/SL prices are also scaled by 1e18
        tp_price = float(trade.get("takeProfitPrice", 0)) / 1e18
        sl_price = float(trade.get("stopLossPrice", 0)) / 1e18

        # Get current price for the pair
        try:
            pair_from = trade["pair"].get("from", "")
            pair_to = trade["pair"].get("to", "USD")
            current_price, _, _ = await sdk.price.get_price(pair_from, pair_to)
        except Exception:
            current_price = 0

        # Calculate PnL: (current_price - open_price) * size * direction
        # Size in units = notional / 1e18, represents position size in base asset
        notional = float(trade.get("tradeNotional", 0)) / 1e18
        if current_price and open_price:
            price_diff = current_price - open_price
            if not is_long:
                price_diff = -price_diff
            pnl = price_diff * notional
        else:
            pnl = 0

        # Calculate liquidation price
        # Liquidation occurs when losses consume the collateral minus a buffer for fees/slippage
        # Using the standard formula: Liq Price = Entry Price * (1 - 1/leverage) for longs
        # This accounts for the fact that at 100% loss of collateral, position is liquidated
        # Adding a small buffer (~1.5%) for liquidation penalty and fees
        liq_buffer = 0.015  # ~1.5% buffer for liquidation costs
        if leverage > 0 and open_price > 0:
            if is_long:
                # Long liquidates when price drops such that losses = collateral
                liq_price = open_price * (1 - (1 - liq_buffer) / leverage)
            else:
                # Short liquidates when price rises such that losses = collateral
                liq_price = open_price * (1 + (1 - liq_buffer) / leverage)
        else:
            liq_price = 0

        table.add_row(
            trade_id,
            pair_name,
            format_direction(is_long),
            f"${collateral:,.2f}",
            f"{leverage:.1f}x",
            f"{open_price:,.2f}",
            f"{current_price:,.2f}" if current_price else "N/A",
            f"{liq_price:,.2f}" if liq_price else "N/A",
            f"{tp_price:,.2f}" if tp_price else "-",
            f"{sl_price:,.2f}" if sl_price else "-",
            format_pnl(pnl) if pnl else "N/A",
        )

    console.print(table)


@app.command()
def trades(
    address: Optional[str] = typer.Option(None, "--address", "-a", help="Wallet address to query (defaults to PRIVATE_KEY)"),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output raw SDK response as JSON"),
) -> None:
    """List open trades with current PnL."""
    run_async(fetch_trades(network, address, output_json))

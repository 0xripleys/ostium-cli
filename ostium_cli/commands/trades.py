"""Command to list open trades with PnL."""

import json
import time
from typing import Any, Optional

import typer
from web3 import Web3

# #region agent log
import os
# #endregion

from ostium_cli.config import Network
from ostium_cli.utils import (
    console,
    create_table,
    format_direction,
    format_pnl,
    get_address,
    get_sdk,
    get_trading_storage_contract,
    run_async,
)

app = typer.Typer()


# Rate limiting settings
BATCH_SIZE = 10  # Max calls per batch to stay under rate limits
BATCH_DELAY = 0.5  # Delay between batches in seconds


def _execute_batched_calls(
    w3: Web3, calls: list[Any], batch_size: int = BATCH_SIZE, delay: float = BATCH_DELAY
) -> list[Any]:
    """Execute contract calls in rate-limited batches."""
    results = []
    for i in range(0, len(calls), batch_size):
        chunk = calls[i : i + batch_size]
        batch = w3.batch_requests()
        for call in chunk:
            batch.add(call)
        results.extend(batch.execute())
        # Add delay between batches to respect rate limits
        if i + batch_size < len(calls):
            time.sleep(delay)
    return results


def fetch_trades_onchain(
    network: Network, address: str, pairs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fetch open trades directly from blockchain using optimized rate-limited RPC calls.

    Optimization strategy:
    1. First, query openTradesCount for all pairs to find which pairs have trades
    2. Only scan slots for pairs with count > 0
    3. Stop scanning a pair early once we've found all expected trades
    """
    w3, trading_storage = get_trading_storage_contract(network)
    checksum_address = Web3.to_checksum_address(address)

    # Get max trades per pair
    max_trades: int = trading_storage.functions.maxTradesPerPair().call()

    # Build pair lookup by index
    pair_by_index = {int(p["id"]): p for p in pairs}

    # PHASE 1: Get trade counts for all pairs
    # This tells us which pairs have trades and how many
    console.print("[dim]Checking trade counts per pair...[/dim]")
    count_calls = []
    for pair in pairs:
        pair_index = int(pair["id"])
        count_calls.append(
            trading_storage.functions.openTradesCount(checksum_address, pair_index)
        )

    count_responses = _execute_batched_calls(w3, count_calls)

    # Build list of pairs that have trades
    pairs_with_trades: list[tuple[int, int, dict[str, Any]]] = []  # (pair_index, count, pair_data)
    total_trades = 0
    for i, count in enumerate(count_responses):
        if count > 0:
            pair = pairs[i]
            pair_index = int(pair["id"])
            pairs_with_trades.append((pair_index, count, pair))
            total_trades += count

    if total_trades == 0:
        return []

    console.print(f"[dim]Found {total_trades} trade(s) across {len(pairs_with_trades)} pair(s). Fetching details...[/dim]")

    # PHASE 2: For pairs with trades, scan slots until we find all trades
    # We need to scan because slots can have gaps (closed trades leave empty slots)
    trade_calls = []
    queries: list[tuple[int, int]] = []  # (pair_index, trade_index)

    for pair_index, expected_count, pair in pairs_with_trades:
        # Scan all slots up to max_trades for this pair
        # We'll filter out empty slots after
        for trade_idx in range(max_trades):
            trade_calls.append(
                trading_storage.functions.getOpenTrade(
                    checksum_address, pair_index, trade_idx
                )
            )
            queries.append((pair_index, trade_idx))

    trade_responses = _execute_batched_calls(w3, trade_calls)

    # PHASE 3: Get trade info only for non-empty slots
    trade_info_calls = []
    active_trades: list[tuple[Any, int, int]] = []  # (trade_data, pair_index, trade_index)

    for i, trade in enumerate(trade_responses):
        # trade[0] is collateral - if > 0, trade exists
        if trade[0] > 0:
            pair_index, trade_idx = queries[i]
            trade_info_calls.append(
                trading_storage.functions.getOpenTradeInfo(
                    checksum_address, pair_index, trade_idx
                )
            )
            active_trades.append((trade, pair_index, trade_idx))

    trade_info_responses = _execute_batched_calls(w3, trade_info_calls) if trade_info_calls else []

    # Combine results into format similar to subgraph response
    trades = []
    for i, (trade, pair_index, trade_idx) in enumerate(active_trades):
        trade_info = trade_info_responses[i]
        pair = pair_by_index.get(pair_index, {})

        # Map on-chain tuple to dict format matching subgraph structure
        # Trade tuple: (collateral, openPrice, tp, sl, trader, leverage, pairIndex, index, buy)
        # TradeInfo tuple: (tradeId, oiNotional, initialLeverage, tpLastUpdated, slLastUpdated, createdAt, beingMarketClosed)
        trades.append({
            "tradeID": str(trade_info[0]),  # tradeId
            "pair": {
                "id": str(pair_index),
                "from": pair.get("from", "???"),
                "to": pair.get("to", "USD"),
            },
            "index": trade[7],  # index
            "isBuy": trade[8],  # buy
            "collateral": trade[0],  # collateral (raw, will be scaled)
            "leverage": trade[5],  # leverage (raw, will be scaled)
            "openPrice": trade[1],  # openPrice (raw, will be scaled)
            "takeProfitPrice": trade[2],  # tp
            "stopLossPrice": trade[3],  # sl
            "tradeNotional": trade_info[1],  # oiNotional
        })

    return trades


async def fetch_trades(
    network: Network,
    address: Optional[str] = None,
    output_json: bool = False,
    onchain: bool = False,
) -> None:
    """Fetch and display open trades."""
    # Use provided address or derive from private key
    if address is None:
        address = get_address()

    sdk = get_sdk(network, require_key=False)

    source = "on-chain" if onchain else "subgraph"
    if not output_json:
        console.print(
            f"Fetching trades for [cyan]{address}[/cyan] on [yellow]{network.value}[/yellow] "
            f"([magenta]{source}[/magenta])..."
        )

    if onchain:
        # Fetch pair metadata from subgraph (rarely changes, needed for pair names)
        pairs = await sdk.subgraph.get_pairs()
        open_trades = fetch_trades_onchain(network, address, pairs)
    else:
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
    address: Optional[str] = typer.Option(
        None, "--address", "-a", help="Wallet address to query (defaults to PRIVATE_KEY)"
    ),
    network: Network = typer.Option(Network.mainnet, "--network", "-n", help="Network to use"),
    output_json: bool = typer.Option(False, "--json", help="Output raw SDK response as JSON"),
    onchain: bool = typer.Option(
        False, "--onchain", help="Fetch trades directly from blockchain (no indexing delay)"
    ),
) -> None:
    """List open trades with current PnL."""
    run_async(fetch_trades(network, address, output_json, onchain))

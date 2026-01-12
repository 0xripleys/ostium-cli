# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ostium CLI is a Python command-line tool for trading on Ostium, a decentralized perpetuals exchange on Arbitrum. It provides market/limit orders, stop-loss management, and trade viewing with real-time PnL calculations.

## Commands

```bash
uv sync                              # Install dependencies
uv run ostium <command> [options]    # Run CLI commands
./tests/e2e_test.sh                  # Run e2e tests (requires testnet funds, jq)
```

Test configuration via env vars: `NETWORK`, `COLLATERAL`, `LEVERAGE`, `INDEXING_DELAY`

## Architecture

**Entry point**: `ostium_cli/main.py` - Typer app registering 7 commands

**Command flow**:
```
Typer CLI args → async command handler → OstiumSDK → Ethereum tx → Rich table or JSON output
```

**Key modules**:
- `ostium_cli/config.py` - Network enum (mainnet/testnet), env var loading (`PRIVATE_KEY`, `RPC_URL_*`)
- `ostium_cli/utils.py` - SDK initialization (`get_sdk()`), address derivation, formatting helpers
- `ostium_cli/commands/*.py` - Command implementations (trades, orders, market, limit, stoploss, cancel, close)

**SDK interaction patterns**:
- Subgraph queries: `sdk.subgraph.get_open_trades()`, `get_orders()`, `get_pairs()`
- Price feeds: `sdk.price.get_price(asset, "USD")`
- Protocol actions: `sdk.ostium.perform_trade()`, `update_sl()`, `close_trade()`, `cancel_limit_order()`

## Code Style

- Use type hints throughout; inline Typer type aliases at point of use (don't declare separately)
- Use uv and ruff (not pip/virtualenv or other linters)
- All commands support `--network {mainnet|testnet}` and `--json` flags
- Async handlers with `run_async()` wrapper for synchronous execution
- Handle SDK return types: `AttributeDict`, `dict`, `HexBytes` (use `.hex()` for tx hashes)

## Number Scaling

SDK values require conversion:
- Collateral: divide by `1e6`
- Leverage: divide by `100`
- Prices: divide by `1e18`

## Environment

- `.env` file loaded via python-dotenv
- Private key must NOT have `0x` prefix
- Networks: Arbitrum One (mainnet) / Arbitrum Sepolia (testnet)

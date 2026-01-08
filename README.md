# Ostium CLI

CLI wrapper for trading on [Ostium](https://ostium.io), a decentralized perpetuals exchange on Arbitrum.

## Installation

```bash
uv sync
```

## Configuration

Create a `.env` file with your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Required - your Arbitrum wallet private key (without 0x prefix)
PRIVATE_KEY=your_private_key_here

# Optional - defaults are provided
RPC_URL_MAINNET=https://arb1.arbitrum.io/rpc
RPC_URL_TESTNET=https://sepolia-rollup.arbitrum.io/rpc
```

## Commands

All commands support `--network mainnet|testnet` (default: mainnet) and `--json` for machine-readable output.

### View Open Trades

```bash
# List all open trades with PnL
uv run ostium trades

# Output as JSON
uv run ostium trades --json
```

Example output:
```
                              Open Trades (1)
┏━━━━━━━━━━┳━━━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Trade ID ┃ Pair    ┃ Dir  ┃ Collat  ┃ Lev  ┃ Entry   ┃ TP      ┃ SL     ┃
┡━━━━━━━━━━╇━━━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ 1161068  │ BTC/USD │ LONG │ $4.88   │ 10x  │ 90,740  │ 172,406 │ -      │
└──────────┴─────────┴──────┴─────────┴──────┴─────────┴─────────┴────────┘
```

### View Open Orders

```bash
# List all pending limit orders
uv run ostium orders

# Output as JSON
uv run ostium orders --json
```

### Create Market Order

```bash
# Open a BTC long position with $10 USDC at 5x leverage
uv run ostium market --asset BTC --direction long --collateral 10 --leverage 5

# Open an ETH short position
uv run ostium market --asset ETH --direction short --collateral 50 --leverage 10

# With JSON output
uv run ostium market --asset BTC --direction long --collateral 10 --leverage 5 --json
```

Example JSON output:
```json
{
  "success": true,
  "transaction_hash": "2052c5bc093c97...",
  "params": {
    "asset": "BTC",
    "pair_index": 0,
    "direction": "long",
    "collateral": 10.0,
    "leverage": 5.0,
    "price": 91290.82
  }
}
```

### Create Limit Order

```bash
# Create a limit order to buy BTC at $80,000
uv run ostium limit --asset BTC --direction long --collateral 10 --leverage 5 --price 80000

# Create a limit order to short ETH at $4,000
uv run ostium limit --asset ETH --direction short --collateral 20 --leverage 3 --price 4000
```

### Set Stop Loss

```bash
# Set stop loss using trade ID (recommended)
uv run ostium stoploss --trade-id 1161068 --price 85000

# Set stop loss using pair index and trade index
uv run ostium stoploss --pair-index 0 --trade-index 0 --price 85000
```

### Cancel Order

```bash
# Cancel a limit order using order ID
uv run ostium cancel --order-id "0x88d3e864c5360ba15fd1af66f28461c235cdd25a_0_0"

# Cancel using pair index and order index
uv run ostium cancel --pair-index 0 --order-index 0
```

### Close Trade

```bash
# Close a trade at market price using trade ID (recommended)
uv run ostium close --trade-id 1161068

# Close using pair index and trade index
uv run ostium close --pair-index 0 --trade-index 0
```

## Supported Assets

| Asset | Pair Index |
|-------|------------|
| BTC   | 0          |
| ETH   | 1          |
| ... and more (see Ostium docs) |

## Testing

Run the end-to-end test suite:

```bash
# On testnet (requires testnet funds)
./tests/e2e_test.sh

# On mainnet (uses real funds - be careful!)
NETWORK=mainnet INDEXING_DELAY=20 ./tests/e2e_test.sh

# With custom parameters
COLLATERAL=5 LEVERAGE=3 INDEXING_DELAY=15 ./tests/e2e_test.sh
```

## JSON Output

All commands support `--json` flag for programmatic use:

```bash
# Get trades as JSON
uv run ostium trades --json | jq '.[0].tradeID'

# Check if order succeeded
uv run ostium market --asset BTC --direction long --collateral 5 --leverage 5 --json | jq '.success'
```

## Networks

- **mainnet** (default): Arbitrum One - real funds
- **testnet**: Arbitrum Sepolia - test funds

```bash
# Use testnet
uv run ostium trades --network testnet

# Explicitly use mainnet
uv run ostium trades --network mainnet
```

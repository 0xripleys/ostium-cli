#!/bin/bash
# Ostium CLI End-to-End Test Script
# Validates all CLI commands using live testnet transactions
#
# Prerequisites:
#   - jq installed for JSON parsing
#   - .env with PRIVATE_KEY containing testnet funds (~50 USDC)
#
# Usage:
#   ./tests/e2e_test.sh                           # Run on testnet (default)
#   NETWORK=mainnet ./tests/e2e_test.sh           # Run on mainnet (with warning)
#   INDEXING_DELAY=5 ./tests/e2e_test.sh          # Custom delay for slow indexing
#   COLLATERAL=5 LEVERAGE=3 ./tests/e2e_test.sh   # Custom trade parameters

set -e

# Configuration
CLI="uv run ostium"
NETWORK_NAME="${NETWORK:-testnet}"
NETWORK="--network $NETWORK_NAME"
ASSET="${ASSET:-BTC}"
COLLATERAL="${COLLATERAL:-10}"
LEVERAGE="${LEVERAGE:-5}"

# Configurable delay for subgraph indexing (default 3 seconds)
INDEXING_DELAY="${INDEXING_DELAY:-3}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Track created resources for cleanup
CREATED_TRADE_ID=""
CREATED_ORDER_ID=""

# ============================================================================
# Helper Functions
# ============================================================================

log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
log_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }
log_phase() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

# Extract JSON from CLI output (SDK may print messages before JSON)
# Looks for content between first { and last }
extract_json() {
    local output="$1"
    # Use perl to extract JSON object (handles multi-line)
    echo "$output" | perl -0777 -ne 'print $1 if /(\{[\s\S]*\})\s*$/'
}

# Wait for subgraph indexing
wait_for_indexing() {
    log_info "Waiting ${INDEXING_DELAY}s for subgraph indexing..."
    sleep "$INDEXING_DELAY"
}

# Check JSON field equals expected value
assert_json_eq() {
    local json="$1"
    local path="$2"
    local expected="$3"
    local actual
    actual=$(echo "$json" | jq -r "$path")
    if [ "$actual" == "$expected" ]; then
        log_pass "$path == $expected"
    else
        log_fail "$path: expected '$expected', got '$actual'"
    fi
}

# Check JSON field is not null/empty
assert_json_exists() {
    local json="$1"
    local path="$2"
    local actual
    actual=$(echo "$json" | jq -r "$path")
    if [ -n "$actual" ] && [ "$actual" != "null" ]; then
        log_pass "$path exists: ${actual:0:50}..."
    else
        log_fail "$path is null or empty"
    fi
}

# Validate transaction hash format (64 hex chars, with or without 0x prefix)
assert_tx_hash() {
    local json="$1"
    local tx
    tx=$(echo "$json" | jq -r '.transaction_hash')
    if [[ "$tx" =~ ^(0x)?[a-fA-F0-9]{64}$ ]]; then
        log_pass "transaction_hash valid: ${tx:0:14}..."
    else
        log_fail "Invalid transaction_hash: $tx"
    fi
}

# Get array length from JSON
get_count() {
    local json="$1"
    echo "$json" | jq 'if type == "array" then length else 0 end'
}

# Check if ID exists in JSON array
id_exists() {
    local json="$1"
    local field="$2"
    local id="$3"
    local found
    found=$(echo "$json" | jq --arg id "$id" --arg field "$field" '[.[] | select(.[$field] == $id)] | length')
    [ "$found" -gt 0 ]
}

# Cleanup function - close trade and cancel order if they exist
cleanup() {
    log_phase "CLEANUP"

    if [ -n "$CREATED_ORDER_ID" ]; then
        log_info "Canceling order $CREATED_ORDER_ID..."
        $CLI cancel $NETWORK --json --order-id "$CREATED_ORDER_ID" 2>/dev/null || true
    fi

    if [ -n "$CREATED_TRADE_ID" ]; then
        log_info "Closing trade $CREATED_TRADE_ID..."
        $CLI close $NETWORK --json --trade-id "$CREATED_TRADE_ID" 2>/dev/null || true
    fi
}

# Set up cleanup trap
trap cleanup EXIT

# ============================================================================
# Main Test Script
# ============================================================================

# Warn if running on mainnet
if [ "$NETWORK_NAME" == "mainnet" ]; then
    echo -e "${RED}WARNING: Running on MAINNET with real funds!${NC}"
    echo "Press Ctrl+C within 5 seconds to abort..."
    sleep 5
fi

echo "=========================================="
echo "   Ostium CLI End-to-End Test"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Network: $NETWORK_NAME"
echo "  Asset: $ASSET"
echo "  Collateral: $COLLATERAL USDC"
echo "  Leverage: ${LEVERAGE}x"
echo "  Indexing delay: ${INDEXING_DELAY}s"
echo ""

# ----------------------------------------------------------------------------
# Phase 1: Baseline
# ----------------------------------------------------------------------------
log_phase "Phase 1: BASELINE"

log_info "Fetching current trades..."
BASELINE_TRADES=$($CLI trades $NETWORK --json)
BASELINE_TRADE_COUNT=$(get_count "$BASELINE_TRADES")
BASELINE_TRADE_IDS=$(echo "$BASELINE_TRADES" | jq -r '.[].tradeID' | tr '\n' '|' | sed 's/|$//')
log_pass "Current trade count: $BASELINE_TRADE_COUNT"

log_info "Fetching current orders..."
BASELINE_ORDERS=$($CLI orders $NETWORK --json)
BASELINE_ORDER_COUNT=$(get_count "$BASELINE_ORDERS")
BASELINE_ORDER_IDS=$(echo "$BASELINE_ORDERS" | jq -r '.[].id' | tr '\n' '|' | sed 's/|$//')
log_pass "Current order count: $BASELINE_ORDER_COUNT"

# ----------------------------------------------------------------------------
# Phase 2: Create Market Order
# ----------------------------------------------------------------------------
log_phase "Phase 2: MARKET ORDER"

log_info "Creating market order: $ASSET LONG, $COLLATERAL USDC, ${LEVERAGE}x"
MARKET_OUTPUT=$($CLI market $NETWORK --json \
    --asset "$ASSET" \
    --direction long \
    --collateral "$COLLATERAL" \
    --leverage "$LEVERAGE" 2>&1)
MARKET_RESULT=$(extract_json "$MARKET_OUTPUT")

assert_json_eq "$MARKET_RESULT" ".success" "true"
assert_tx_hash "$MARKET_RESULT"
assert_json_eq "$MARKET_RESULT" ".params.asset" "$ASSET"
assert_json_eq "$MARKET_RESULT" ".params.direction" "long"

# ----------------------------------------------------------------------------
# Phase 3: Verify Trade Created
# ----------------------------------------------------------------------------
log_phase "Phase 3: VERIFY TRADE CREATED"

wait_for_indexing

log_info "Fetching trades after market order..."
TRADES_AFTER_MARKET=$($CLI trades $NETWORK --json)
TRADE_COUNT_AFTER_MARKET=$(get_count "$TRADES_AFTER_MARKET")
EXPECTED_TRADE_COUNT=$((BASELINE_TRADE_COUNT + 1))

if [ "$TRADE_COUNT_AFTER_MARKET" -eq "$EXPECTED_TRADE_COUNT" ]; then
    log_pass "Trade count increased: $BASELINE_TRADE_COUNT -> $TRADE_COUNT_AFTER_MARKET"
else
    log_fail "Trade count mismatch: expected $EXPECTED_TRADE_COUNT, got $TRADE_COUNT_AFTER_MARKET"
fi

# Capture new trade ID (find the one that's not in baseline)
if [ -n "$BASELINE_TRADE_IDS" ]; then
    CREATED_TRADE_ID=$(echo "$TRADES_AFTER_MARKET" | jq -r '.[].tradeID' | grep -v -E "^($BASELINE_TRADE_IDS)$" | head -1)
else
    # No baseline trades, so the first one is the new one
    CREATED_TRADE_ID=$(echo "$TRADES_AFTER_MARKET" | jq -r '.[0].tradeID')
fi
log_info "New trade ID: $CREATED_TRADE_ID"

# Get entry price for stop loss calculation (for the new trade)
ENTRY_PRICE=$(echo "$TRADES_AFTER_MARKET" | jq -r --arg id "$CREATED_TRADE_ID" '.[] | select(.tradeID == $id) | .openPrice')
ENTRY_PRICE_SCALED=$(echo "scale=2; $ENTRY_PRICE / 1000000000000000000" | bc)
log_info "Entry price: $ENTRY_PRICE_SCALED"

# ----------------------------------------------------------------------------
# Phase 4: Set Stop Loss
# ----------------------------------------------------------------------------
log_phase "Phase 4: STOPLOSS"

# Set stop loss at 93% of entry price (must be above liquidation price)
SL_PRICE=$(echo "scale=0; $ENTRY_PRICE_SCALED * 0.93 / 1" | bc)
log_info "Setting stop loss at $SL_PRICE (93% of entry)"

STOPLOSS_OUTPUT=$($CLI stoploss $NETWORK --json \
    --trade-id "$CREATED_TRADE_ID" \
    --price "$SL_PRICE" 2>&1)
STOPLOSS_RESULT=$(extract_json "$STOPLOSS_OUTPUT")

assert_json_eq "$STOPLOSS_RESULT" ".success" "true"
assert_tx_hash "$STOPLOSS_RESULT"

# ----------------------------------------------------------------------------
# Phase 5: Verify Stop Loss Set
# ----------------------------------------------------------------------------
log_phase "Phase 5: VERIFY STOP LOSS"

wait_for_indexing

log_info "Checking stop loss was set..."
TRADES_AFTER_SL=$($CLI trades $NETWORK --json)
SL_VALUE=$(echo "$TRADES_AFTER_SL" | jq -r --arg id "$CREATED_TRADE_ID" '.[] | select(.tradeID == $id) | .stopLossPrice')

if [ -n "$SL_VALUE" ] && [ "$SL_VALUE" != "0" ] && [ "$SL_VALUE" != "null" ]; then
    SL_SCALED=$(echo "scale=2; $SL_VALUE / 1000000000000000000" | bc)
    log_pass "Stop loss set: $SL_SCALED"
else
    log_fail "Stop loss not found on trade"
fi

# ----------------------------------------------------------------------------
# Phase 6: Create Limit Order
# ----------------------------------------------------------------------------
log_phase "Phase 6: LIMIT ORDER"

# Set limit price at 50% of current market (will not execute)
LIMIT_PRICE=$(echo "scale=0; $ENTRY_PRICE_SCALED * 0.5 / 1" | bc)
log_info "Creating limit order at $LIMIT_PRICE (50% of market)"

LIMIT_OUTPUT=$($CLI limit $NETWORK --json \
    --asset "$ASSET" \
    --direction long \
    --collateral "$COLLATERAL" \
    --leverage "$LEVERAGE" \
    --price "$LIMIT_PRICE" 2>&1)
LIMIT_RESULT=$(extract_json "$LIMIT_OUTPUT")

assert_json_eq "$LIMIT_RESULT" ".success" "true"
assert_tx_hash "$LIMIT_RESULT"

# ----------------------------------------------------------------------------
# Phase 7: Verify Order Created
# ----------------------------------------------------------------------------
log_phase "Phase 7: VERIFY ORDER CREATED"

wait_for_indexing

log_info "Fetching orders after limit order..."
ORDERS_AFTER_LIMIT=$($CLI orders $NETWORK --json)
ORDER_COUNT_AFTER_LIMIT=$(get_count "$ORDERS_AFTER_LIMIT")
EXPECTED_ORDER_COUNT=$((BASELINE_ORDER_COUNT + 1))

if [ "$ORDER_COUNT_AFTER_LIMIT" -eq "$EXPECTED_ORDER_COUNT" ]; then
    log_pass "Order count increased: $BASELINE_ORDER_COUNT -> $ORDER_COUNT_AFTER_LIMIT"
else
    log_fail "Order count mismatch: expected $EXPECTED_ORDER_COUNT, got $ORDER_COUNT_AFTER_LIMIT"
fi

# Capture new order ID (find the one that's not in baseline)
if [ -n "$BASELINE_ORDER_IDS" ]; then
    CREATED_ORDER_ID=$(echo "$ORDERS_AFTER_LIMIT" | jq -r '.[].id' | grep -v -E "^($BASELINE_ORDER_IDS)$" | head -1)
else
    # No baseline orders, so the first one is the new one
    CREATED_ORDER_ID=$(echo "$ORDERS_AFTER_LIMIT" | jq -r '.[0].id')
fi
log_info "New order ID: $CREATED_ORDER_ID"

# ----------------------------------------------------------------------------
# Phase 8: Cancel Limit Order
# ----------------------------------------------------------------------------
log_phase "Phase 8: CANCEL ORDER"

log_info "Canceling order $CREATED_ORDER_ID..."
CANCEL_OUTPUT=$($CLI cancel $NETWORK --json \
    --order-id "$CREATED_ORDER_ID" 2>&1)
CANCEL_RESULT=$(extract_json "$CANCEL_OUTPUT")

assert_json_eq "$CANCEL_RESULT" ".success" "true"
assert_tx_hash "$CANCEL_RESULT"

# ----------------------------------------------------------------------------
# Phase 9: Verify Order Canceled
# ----------------------------------------------------------------------------
log_phase "Phase 9: VERIFY ORDER CANCELED"

wait_for_indexing

log_info "Fetching orders after cancel..."
ORDERS_AFTER_CANCEL=$($CLI orders $NETWORK --json)
ORDER_COUNT_AFTER_CANCEL=$(get_count "$ORDERS_AFTER_CANCEL")

if [ "$ORDER_COUNT_AFTER_CANCEL" -eq "$BASELINE_ORDER_COUNT" ]; then
    log_pass "Order count returned to baseline: $ORDER_COUNT_AFTER_CANCEL"
else
    log_fail "Order count mismatch: expected $BASELINE_ORDER_COUNT, got $ORDER_COUNT_AFTER_CANCEL"
fi

# Clear the order ID since it's been canceled
CREATED_ORDER_ID=""

# ----------------------------------------------------------------------------
# Phase 10: Close Trade
# ----------------------------------------------------------------------------
log_phase "Phase 10: CLOSE TRADE"

log_info "Closing trade $CREATED_TRADE_ID..."
CLOSE_OUTPUT=$($CLI close $NETWORK --json \
    --trade-id "$CREATED_TRADE_ID" 2>&1)
CLOSE_RESULT=$(extract_json "$CLOSE_OUTPUT")

assert_json_eq "$CLOSE_RESULT" ".success" "true"
assert_tx_hash "$CLOSE_RESULT"

# ----------------------------------------------------------------------------
# Phase 11: Verify Trade Closed
# ----------------------------------------------------------------------------
log_phase "Phase 11: VERIFY TRADE CLOSED"

wait_for_indexing

log_info "Fetching trades after close..."
TRADES_FINAL=$($CLI trades $NETWORK --json)
FINAL_TRADE_COUNT=$(get_count "$TRADES_FINAL")

if [ "$FINAL_TRADE_COUNT" -eq "$BASELINE_TRADE_COUNT" ]; then
    log_pass "Trade count returned to baseline: $FINAL_TRADE_COUNT"
else
    log_fail "Trade count mismatch: expected $BASELINE_TRADE_COUNT, got $FINAL_TRADE_COUNT"
fi

# Verify trade ID no longer exists
if ! id_exists "$TRADES_FINAL" "tradeID" "$CREATED_TRADE_ID"; then
    log_pass "Trade $CREATED_TRADE_ID no longer in open trades"
else
    log_fail "Trade $CREATED_TRADE_ID still exists after close"
fi

# Clear the trade ID since it's been closed
CREATED_TRADE_ID=""

# ----------------------------------------------------------------------------
# Final Summary
# ----------------------------------------------------------------------------
log_phase "FINAL SUMMARY"

echo ""
echo "=========================================="
echo -e "${GREEN}All tests passed!${NC}"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - trades command: verified"
echo "  - orders command: verified"
echo "  - market command: created and verified trade"
echo "  - stoploss command: set stop loss on trade"
echo "  - limit command: created and verified order"
echo "  - cancel command: canceled order successfully"
echo "  - close command: closed trade successfully"
echo ""
echo "Final state matches baseline:"
echo "  - Trades: $FINAL_TRADE_COUNT (was $BASELINE_TRADE_COUNT)"
echo "  - Orders: $ORDER_COUNT_AFTER_CANCEL (was $BASELINE_ORDER_COUNT)"
echo ""

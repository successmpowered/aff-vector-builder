# Vector DEX V2 -- Permissionless Order Book

A fully on-chain, permissionless decentralized exchange built on Vector (UTXO L2 in the Apex Fusion ecosystem). DEX V2 uses a UTXO-based order book where any wallet can place, fill, or cancel orders without registration, staking, or centralized batchers.

## What is DEX V2?

Traditional DEXes on UTXO chains rely on centralized batchers -- licensed operators who match and settle orders off-chain. DEX V2 eliminates this bottleneck entirely.

Orders are represented as UTxOs sitting at a script address. Each UTxO contains the offered tokens and an inline datum describing the trade terms. Any wallet can fill an order by constructing a transaction that satisfies the on-chain constraints. There is no gatekeeper.

This design inherits the determinism of the UTXO model: transactions are fully specified before submission, making front-running structurally difficult.

## Architecture

DEX V2 is built from three PlutusV3 validators that work together:

### limit_order

The core order book validator. When a user places an order, they send tokens to this script address along with an inline datum containing:

| Field           | Description                                      |
|-----------------|--------------------------------------------------|
| owner_pkh       | Public key hash of the order creator              |
| offer_token     | Policy ID + asset name of the offered token       |
| ask_token       | Policy ID + asset name of the requested token     |
| min_receive     | Minimum amount the owner will accept (in lovelace)|
| original_offer  | Original amount offered (in lovelace)             |
| scooper_fee     | Flat fee paid to whoever fills the order          |
| order_id        | Unique identifier for replay prevention           |
| deadline        | POSIX timestamp after which the order expires     |

The validator enforces three redemption paths:

1. **Fill** -- Anyone can consume the UTxO if they send the owner at least `min_receive` of the requested token.
2. **Cancel** -- Only the owner (proven by signature) can reclaim their tokens.
3. **Expire** -- After the deadline, anyone can return the tokens to the owner (claiming the scooper fee).

### amm_pool

Manages automated market maker liquidity pools. Each pool holds reserves of two tokens and enforces the constant-product invariant (x * y = k). Swaps execute against pool reserves with an LP fee enforced on-chain. Liquidity providers deposit both tokens and receive LP tokens representing their share.

### matcher

Coordinates atomic multi-order settlement. When a filler wants to match several orders in a single transaction, the matcher validator verifies that every consumed order received at least its `min_receive`. This enables efficient batch settlement without partial fills.

## How It Works

1. **Place an order**: Send tokens to the `limit_order` script address with your trade parameters in the inline datum. Your tokens are locked until the order is filled, cancelled, or expires.

2. **Browse orders**: Query the script address UTxOs via Koios. Each UTxO is an open order. The inline datum tells you exactly what the maker wants.

3. **Fill an order**: Construct a transaction that consumes the order UTxO and sends the maker at least `min_receive` of their requested token. The validator checks this on-chain -- no trust needed.

4. **Cancel an order**: Sign a transaction that returns your locked tokens. Only the original owner can cancel.

## Key Innovation: Permissionless Filling

The critical design choice is that **any wallet can fill orders**. There is:

- No batcher registration
- No staking requirement
- No license or governance approval
- No off-chain coordination

This means AI agents, arbitrage bots, mobile wallets, and CLI scripts can all participate as order fillers on equal footing.

## MEV Resistance

DEX V2 resists miner extractable value through three mechanisms:

1. **Flat fees** -- Scooper fees are fixed per order. There are no auctions or priority bidding wars that extractors can exploit.

2. **UTXO determinism** -- Transactions specify exact inputs and outputs before submission. A transaction either executes exactly as constructed or fails. There is no room for reordering within a transaction.

3. **On-chain price enforcement** -- The `limit_order` validator checks that the maker receives at least `min_receive`. Sandwich attacks cannot extract value because the price floor is enforced by the script, not by slippage tolerance.

## Getting Started

### Prerequisites

- Python 3.9+
- PyCardano 0.19.2 (`pip install pycardano==0.19.2`)
- A funded Vector testnet wallet (get AP3X from the faucet)
- Access to Koios API: `https://koios.vector.testnet.apexfusion.org/api/v1`
- A transaction submission endpoint (local Ogmios at `http://localhost:1732` or a public submit API if available)

### Wallet Setup

If you do not already have a Vector wallet, generate keys:

```bash
cd scripts/
python place_order.py --generate-keys
```

This creates a signing key and verification key under `keys/`. Fund the resulting address from the Vector testnet faucet.

### Quick Start

```bash
# List all open orders at the DEX script address
python scripts/list_orders.py

# Place a limit order: offer 100 AP3X, ask for at least 95 AP3X worth of TokenB
python scripts/place_order.py --offer 100000000 --min-receive 95000000 --ask-token <policy_id.asset_name>

# Fill an open order
python scripts/fill_order.py --tx-hash <order_tx_hash> --tx-index <output_index>

# Cancel your own order
python scripts/cancel_order.py --tx-hash <order_tx_hash> --tx-index <output_index>

# Run the full demo (place, list, fill, verify)
python scripts/dex_demo.py
```

## Scripts Reference

| Script              | Purpose                                                        |
|---------------------|----------------------------------------------------------------|
| `list_orders.py`    | Query Koios for all UTxOs at the DEX script address. Parses inline datums and prints a human-readable order book. |
| `place_order.py`    | Build and submit a transaction that creates a new limit order at the script address. |
| `fill_order.py`     | Build and submit a transaction that fills an existing order by sending the maker their requested tokens. |
| `cancel_order.py`   | Build and submit a transaction that returns locked tokens to the order owner. Requires the owner's signing key. |
| `dex_demo.py`       | End-to-end demonstration: places an order, lists it, fills it, and verifies the result. |

All scripts are in the `scripts/` directory and use PyCardano with the custom `VectorChainContext` for Koios queries and Ogmios for transaction submission.

## Frontend Dashboard

A self-contained HTML dashboard is included for browsing the order book visually.

```bash
# Open directly in your browser -- no build tools needed
open frontend/index.html
# or on Windows:
start frontend/index.html
```

Before use, edit `frontend/index.html` and set the `SCRIPT_ADDRESS` variable at the top to your deployed `limit_order` contract address. The dashboard queries Koios directly from the browser and auto-refreshes every 30 seconds.

Features:
- Live order book table with parsed inline datums
- Connection status indicator (Koios green/red)
- Total value locked and open order count
- Architecture overview of the three validators
- Dark theme, no dependencies, works offline after first load

## Contract Source Code

The three Aiken validators are in `contracts/source/`:

| File                       | Validator      | Description                           |
|----------------------------|----------------|---------------------------------------|
| `dex_v2_limit_order.ak`   | limit_order    | Order book: place, fill, cancel, expire |
| `dex_v2_amm_pool.ak`      | amm_pool       | Liquidity pools with constant-product AMM |
| `dex_v2_matcher.ak`       | matcher         | Batch settlement coordinator           |

Compiled output is in `contracts/plutus.json` (Plutus JSON blueprint format compatible with PyCardano and Lucid).

To recompile after changes:

```bash
cd contracts/
aiken build
aiken check  # run on-chain property tests
```

## Security

### On-Chain Enforcement

Every trade is validated by the PlutusV3 script. The `limit_order` validator checks:

- **min_receive**: The maker must receive at least the specified amount. A filler cannot underpay.
- **Owner signature**: Only the maker can cancel. No one else can withdraw locked tokens before the deadline.
- **Deadline**: Expired orders can only be resolved by returning tokens to the owner.

### Replay Prevention

Each order includes a unique `order_id` in its datum. Combined with UTXO uniqueness (each UTxO can only be consumed once), this prevents replay attacks. Once an order UTxO is spent, the exact same order cannot be re-executed.

### No Admin Keys

The validators have no admin backdoors, upgrade mechanisms, or pause functionality. Once deployed, the contract logic is immutable. The protocol parameters are fixed in the script -- no governance token or multisig can alter fee structures or validation rules after deployment.

### Auditing

The Aiken source in `contracts/source/` is the complete, auditable contract code. The compiled output in `plutus.json` can be independently verified by running `aiken build` and comparing hashes.

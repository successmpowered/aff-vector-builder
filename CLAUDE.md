# Vector Builder Kit

## What This Is
A self-contained toolkit for building on Vector, a UTXO L2 blockchain in the Apex Fusion ecosystem. Contains two projects:
- **DEX V2**: Permissionless order book DEX (3 PlutusV3 validators)
- **AI Assembly**: 5 governance validators (council, registry, governance, forum, treasury)

## Network Configuration
- **Chain**: Vector Testnet (Cardano protocol, Conway era, PlutusV3)
- **Address prefix**: `addr1` (use `Network.MAINNET` in PyCardano)
- **Native coin**: AP3X (1 AP3X = 1,000,000 lovelace)
- **Koios API** (read-only): `https://koios.vector.testnet.apexfusion.org/api/v1`
- **Ogmios** (query/evaluate): `https://ogmios.vector.testnet.apexfusion.org` (public — no local node needed)
- **Submit REST API**: `https://submit.vector.testnet.apexfusion.org` (public — no local node needed)
- **Block time**: ~6-7 seconds
- **Min UTxO**: 2,000,000 lovelace (2 AP3X)

## Working Stack
- **Python 3.9+** with PyCardano 0.19.2 (the ONLY working SDK)
- **Aiken v1.1.19** for smart contract compilation (contracts are pre-compiled in `plutus.json`)
- **Node.js libraries (Lucid, MeshJS) are BROKEN** on Node v24+ (libsodium ESM bug) — do NOT try them

## Critical PyCardano Quirks
- `TransactionBuilder` auto-UTxO selection is broken with custom ChainContext — ALWAYS use manual `add_input()`
- Koios returns `max_bh_size` (not `max_block_header_size`) — handled in VectorChainContext
- Must set `coins_per_utxo_word=0` (deprecated but PyCardano requires it) — handled in VectorChainContext
- Inline datums using `RawPlutusData` with large CBOR data may be rejected (indefinite-length encoding). For large datums, use `datum_hash` approach instead.

## Key Files
- `shared/vector_chain_context.py` — The PyCardano ChainContext for Vector. ALL scripts depend on this.
- `shared/helpers.py` — Common utilities (wallet loading, UTxO selection, tx submission, script loading)
- `shared/requirements.txt` — Python dependencies (`pip install -r shared/requirements.txt`)
- `dex-v2/contracts/plutus.json` — Pre-compiled DEX validators (28KB)
- `ai-assembly/contracts/plutus.json` — Pre-compiled Assembly validators (5 governance contracts)

## How Scripts Work
All Python scripts import from `shared/` using relative path manipulation:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext
```

## Wallet
Keys live in `wallet/` at the kit root. Generate with `python setup/generate_wallet.py`.
Fund from the Vector faucet on Discord. Check balance: `python setup/check_balance.py`.

## Transaction Submission
Public endpoints are available — **no local node or Docker required**:
- Ogmios (UTxO queries + tx evaluation): `https://ogmios.vector.testnet.apexfusion.org`
- Submit REST API: `https://submit.vector.testnet.apexfusion.org`

These are the defaults in `VectorChainContext`. All scripts work out of the box.

A local Docker node is still an option for offline development or if public endpoints are unavailable:
```
cd docker
docker compose up -d
# Wait 3-4 hours for initial sync
ctx = VectorChainContext(ogmios_url="http://localhost:1732", submit_url=None)
```
Windows users: run `python setup/fix_crlf.py` first (fixes CRLF line endings in genesis files).

## Datum Encoding Patterns
- Simple value: `RawPlutusData(42)` or `RawPlutusData(b'\xab\xcd')`
- Constructor 0: `RawPlutusData(cbor2.CBORTag(121, [field1, field2, ...]))`
- Constructor 1: `RawPlutusData(cbor2.CBORTag(122, [field1, field2, ...]))`
- Constructor 2: `RawPlutusData(cbor2.CBORTag(123, []))`
- Bool False = `cbor2.CBORTag(121, [])`, Bool True = `cbor2.CBORTag(122, [])`

## When Helping Users
- If they're exploring: suggest read-only scripts first (01_check_balance.py, list_orders.py)
- If they want to transact: wallet just needs to be funded — public endpoints handle the rest (no Docker needed)
- If something fails with "script evaluation failed": check datum shape matches what the validator expects
- If "insufficient funds": need at least 2 AP3X per output + fees + collateral (4+ AP3X for script spends)
- Smart contract source is in `contracts/source/*.ak` — read these to understand validator logic
- AI Assembly uses 5 governance validators: council, registry, governance, forum, treasury
- DEX V2 uses 3 validators: limit_order, amm_pool, matcher

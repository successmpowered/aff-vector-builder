"""
deploy_escrow.py - Lock and unlock AP3X in the treasury validator

Demonstrates the fundamental lock/unlock pattern on Vector:
1. Lock 2 AP3X at the treasury script address with a datum
2. Wait for confirmation
3. Unlock by spending the script UTxO with a redeemer

Requires: Local Ogmios at localhost:1732 (synced Vector node)

Usage:
    python deploy_escrow.py
    python deploy_escrow.py --wallet ../../wallet
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import cbor2
import time
import argparse

# ── Configuration ─────────────────────────────────────────────────────────

PLUTUS_JSON = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'plutus.json')
DEFAULT_WALLET = os.path.join(os.path.dirname(__file__), '..', '..', 'wallet')
LOCK_AMOUNT = 2_000_000  # 2 AP3X

parser = argparse.ArgumentParser(description="Lock & unlock AP3X in treasury validator")
parser.add_argument("--wallet", default=DEFAULT_WALLET, help="Path to wallet directory")
args = parser.parse_args()

# ── Load wallet and script ───────────────────────────────────────────────

print("=" * 60)
print("TREASURY VALIDATOR - Lock & Unlock Demo")
print("=" * 60)

sk, vk, address = load_wallet(args.wallet)
pkh = vk.hash()
print(f"\nWallet: {address}")
print(f"PKH:    {pkh.payload.hex()}")

script, sh, script_address = load_script(PLUTUS_JSON, 'treasury.treasury.spend')
print(f"Script: {script_address}")
print(f"Hash:   {sh.payload.hex()}")

# ── Query wallet UTxOs ────────────────────────────────────────────────────

ctx = VectorChainContext()
utxos_raw = query_utxos_ogmios(address)

if not utxos_raw:
    print("\nERROR: No UTxOs found. Fund your wallet first.")
    sys.exit(1)

print(f"\nWallet UTxOs:")
print_utxo_summary(utxos_raw)

# ── Step 1: Lock 2 AP3X at treasury script ────────────────────────────────

print("\n--- STEP 1: Locking 2 AP3X at treasury script ---")

# Treasury datum: TFunds = Constructor 1 (CBORTag 122, no fields)
datum = RawPlutusData(cbor2.CBORTag(122, []))

funding_utxo_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 1_000_000)
if not funding_utxo_raw:
    print("ERROR: No suitable UTxO found. Need at least 3 AP3X.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_utxo_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(
    script_address,
    LOCK_AMOUNT,
    datum=datum,
))

lock_tx = builder.build_and_sign(
    signing_keys=[sk],
    change_address=address,
)

lock_tx_hash = submit_tx(lock_tx, label="treasury-lock")
print(f"Lock TX submitted: {lock_tx_hash}")

# ── Wait for lock to confirm ──────────────────────────────────────────────

print("\nWaiting 10 seconds for lock transaction to confirm...")
time.sleep(10)

# ── Step 2: Unlock from treasury ──────────────────────────────────────────

print("\n--- STEP 2: Unlocking from treasury script ---")

# Find the script UTxO we just locked
script_utxos = ctx.utxos(script_address)
our_utxo = None
for u in script_utxos:
    val = u.output.amount if isinstance(u.output.amount, int) else u.output.amount.coin
    if val == LOCK_AMOUNT:
        our_utxo = u
        break

if our_utxo is None:
    print("WARNING: Could not find script UTxO. It may not be confirmed yet.")
    print("Try running again after the node catches up.")
    sys.exit(0)

print(f"Found script UTxO: {our_utxo.input.transaction_id.payload.hex()[:16]}...#{our_utxo.input.index}")

# Build unlock transaction
redeemer = Redeemer(RawPlutusData(0), ExecutionUnits(2_000_000, 1_000_000_000))

# Need a fresh UTxO for fees and collateral
wallet_utxos = ctx.utxos(address)
fee_utxo = None
for u in wallet_utxos:
    val = u.output.amount if isinstance(u.output.amount, int) else u.output.amount.coin
    if val >= 5_000_000:
        fee_utxo = u
        break

if fee_utxo is None:
    print("ERROR: No UTxO available for fees/collateral (need 5+ AP3X).")
    sys.exit(1)

unlock_builder = TransactionBuilder(ctx)
unlock_builder.add_script_input(
    our_utxo,
    script=script,
    datum=datum,
    redeemer=redeemer,
)
unlock_builder.add_input(fee_utxo)
unlock_builder.collaterals = [fee_utxo]

unlock_tx = unlock_builder.build_and_sign(
    signing_keys=[sk],
    change_address=address,
)

unlock_tx_hash = submit_tx(unlock_tx, label="treasury-unlock")
print(f"Unlock TX submitted: {unlock_tx_hash}")

# ── Summary ───────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("TREASURY LOCK/UNLOCK DEMO COMPLETE")
print(f"  Lock TX:   {lock_tx_hash}")
print(f"  Unlock TX: {unlock_tx_hash}")
print("=" * 60)

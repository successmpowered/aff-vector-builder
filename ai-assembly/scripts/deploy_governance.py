"""
deploy_governance.py - Simplified governance lifecycle demo

Demonstrates on-chain governance on Vector:
1. Register a member via the registry validator
2. Confirm the registration UTxO exists on-chain
3. Submit a governance proposal via the governance validator

Requires: Local Ogmios at localhost:1732 (synced Vector node)
Note: Full voting lifecycle requires multiple wallets and is beyond this demo.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import cbor2
import time

# ── Configuration ─────────────────────────────────────────────────────────

PLUTUS_JSON = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'plutus.json')
WALLET_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'wallet')
LOCK_AMOUNT = 2_000_000  # 2 AP3X

# ── Load wallet and scripts ──────────────────────────────────────────────

print("=" * 60)
print("GOVERNANCE LIFECYCLE - Register & Propose Demo")
print("=" * 60)

sk, vk, address = load_wallet(WALLET_DIR)
pkh = vk.hash()
print(f"\nWallet: {address}")

# Load registry validator
reg_script, reg_sh, reg_address = load_script(PLUTUS_JSON, 'registry.registry.spend')
print(f"\nRegistry script: {reg_address}")
print(f"  Hash: {reg_sh.payload.hex()}")

# Load governance validator
gov_script, gov_sh, gov_address = load_script(PLUTUS_JSON, 'governance.governance.spend')
print(f"Governance script: {gov_address}")
print(f"  Hash: {gov_sh.payload.hex()}")

# ── Query wallet UTxOs ────────────────────────────────────────────────────

ctx = VectorChainContext()
utxos_raw = query_utxos_ogmios(address)

if not utxos_raw:
    print("\nERROR: No UTxOs found. Fund your wallet first.")
    sys.exit(1)

total_balance = sum(u["value"]["ada"]["lovelace"] for u in utxos_raw)
print(f"\nWallet balance: {format_ap3x(total_balance)}")

# Need at least 6 AP3X: 2 for registration + 2 for proposal + 2 for fees
if total_balance < 6_000_000:
    print("ERROR: Need at least 6 AP3X (2 registration + 2 proposal + 2 fees).")
    sys.exit(1)

# ── Step 1: Register member via registry validator ────────────────────────

print("\n--- STEP 1: Registering member in registry ---")

# Datum: just the member's public key hash (simple registration)
reg_datum = RawPlutusData(bytes(pkh))

funding_utxo_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 2_000_000)
if not funding_utxo_raw:
    print("ERROR: No suitable UTxO found.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_utxo_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(
    reg_address,
    LOCK_AMOUNT,
    datum=reg_datum,
))

reg_tx = builder.build_and_sign(
    signing_keys=[sk],
    change_address=address,
)

reg_tx_hash = submit_tx(reg_tx, label="registry-register")
print(f"Registration TX submitted: {reg_tx_hash}")

# ── Wait and confirm registration ─────────────────────────────────────────

print("\nWaiting 10 seconds for registration to confirm...")
time.sleep(10)

# Query registry script address to confirm
reg_utxos = ctx.utxos(reg_address)
found_registration = False
for u in reg_utxos:
    val = u.output.amount if isinstance(u.output.amount, int) else u.output.amount.coin
    if val == LOCK_AMOUNT:
        found_registration = True
        print(f"Registration confirmed! UTxO: {u.input.transaction_id.payload.hex()[:16]}...#{u.input.index}")
        break

if not found_registration:
    print("WARNING: Registration UTxO not yet visible. Node may need more time to sync.")
    print("Continuing with proposal submission anyway...")

# ── Step 2: Submit governance proposal ────────────────────────────────────

print("\n--- STEP 2: Submitting governance proposal ---")

# Datum: Constructor 0 with [description, proposer_pkh, vote_count=0]
proposal_description = b'Upgrade protocol'
gov_datum = RawPlutusData(cbor2.CBORTag(121, [
    proposal_description,
    bytes(pkh),
    0,  # initial vote count
]))

# Get fresh UTxOs (balance changed after registration)
utxos_raw = query_utxos_ogmios(address)
funding_utxo_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 1_000_000)
if not funding_utxo_raw:
    print("ERROR: No suitable UTxO found for proposal.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_utxo_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(
    gov_address,
    LOCK_AMOUNT,
    datum=gov_datum,
))

gov_tx = builder.build_and_sign(
    signing_keys=[sk],
    change_address=address,
)

gov_tx_hash = submit_tx(gov_tx, label="governance-propose")
print(f"Proposal TX submitted: {gov_tx_hash}")
print("Proposal submitted on-chain!")

# ── Summary ───────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("GOVERNANCE DEMO COMPLETE")
print(f"  Registration TX: {reg_tx_hash}")
print(f"  Proposal TX:     {gov_tx_hash}")
print(f"  Proposal:        'Upgrade protocol'")
print(f"  Proposer:        {pkh.payload.hex()[:32]}...")
print()
print("Note: Full voting lifecycle requires multiple wallets to cast")
print("votes and a council to ratify. This demo shows the registration")
print("and proposal submission steps.")
print("=" * 60)

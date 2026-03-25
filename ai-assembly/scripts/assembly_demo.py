"""
assembly_demo.py - End-to-end multi-validator deployment demo

Runs through multiple AI Assembly validators in sequence:
1. Check wallet balance (need at least 10 AP3X)
2. Deploy to treasury: lock 2 AP3X
3. Deploy to registry: lock 2 AP3X (register member)
4. Deploy to forum: lock 2 AP3X (publish post)
5. Print summary

This demo performs lock transactions only (no unlocking).
Unlocking requires a local Ogmios with sufficient collateral and
the node fully synced to chain tip.

Requires: Local Ogmios at localhost:1732 (synced Vector node)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import cbor2
import time
import hashlib

# ── Configuration ─────────────────────────────────────────────────────────

PLUTUS_JSON = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'plutus.json')
WALLET_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'wallet')
LOCK_AMOUNT = 2_000_000  # 2 AP3X per validator

# ── Load wallet ───────────────────────────────────────────────────────────

print("=" * 60)
print("AI ASSEMBLY - Multi-Validator Deployment Demo")
print("=" * 60)

sk, vk, address = load_wallet(WALLET_DIR)
pkh = vk.hash()
print(f"\nWallet: {address}")

ctx = VectorChainContext()

# ── Step 0: Check balance ─────────────────────────────────────────────────

print("\n--- Checking wallet balance ---")
utxos_raw = query_utxos_ogmios(address)

if not utxos_raw:
    print("ERROR: No UTxOs found. Fund your wallet first.")
    sys.exit(1)

total_balance = sum(u["value"]["ada"]["lovelace"] for u in utxos_raw)
print(f"Balance: {format_ap3x(total_balance)}")

# Need: 3 locks * 2 AP3X + fees (~2 AP3X) = ~8 AP3X minimum, require 10 for safety
required = 10_000_000
if total_balance < required:
    print(f"ERROR: Need at least {format_ap3x(required)}")
    print(f"  Current balance: {format_ap3x(total_balance)}")
    print(f"  Shortfall: {format_ap3x(required - total_balance)}")
    sys.exit(1)

print(f"Balance sufficient ({format_ap3x(total_balance)} >= {format_ap3x(required)})")

# ── Load all validators ───────────────────────────────────────────────────

print("\n--- Loading validators ---")

treasury_script, treasury_sh, treasury_addr = load_script(PLUTUS_JSON, 'treasury.treasury.spend')
print(f"  Treasury: {treasury_addr}")

reg_script, reg_sh, reg_addr = load_script(PLUTUS_JSON, 'registry.registry.spend')
print(f"  Registry: {reg_addr}")

forum_script, forum_sh, forum_addr = load_script(PLUTUS_JSON, 'forum.forum.spend')
print(f"  Forum:    {forum_addr}")

tx_hashes = []

# ── Step 1: Deploy to escrow ──────────────────────────────────────────────

print("\n--- [1/3] Deploying to treasury validator ---")

# Treasury datum: TFunds = Constructor 1 (CBORTag 122, no fields)
treasury_datum = RawPlutusData(cbor2.CBORTag(122, []))

funding_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 2_000_000)
if not funding_raw:
    print("ERROR: No suitable UTxO for treasury lock.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(treasury_addr, LOCK_AMOUNT, datum=treasury_datum))

tx = builder.build_and_sign(signing_keys=[sk], change_address=address)
treasury_hash = submit_tx(tx, label="assembly-treasury")
tx_hashes.append(("Treasury", treasury_hash))
print(f"  TX: {treasury_hash}")

# Wait for UTxO set to update
print("  Waiting 10 seconds...")
time.sleep(10)

# ── Step 2: Deploy to registry ────────────────────────────────────────────

print("\n--- [2/3] Deploying to registry validator ---")

reg_datum = RawPlutusData(bytes(pkh))

# Refresh UTxOs after previous tx
utxos_raw = query_utxos_ogmios(address)
funding_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 2_000_000)
if not funding_raw:
    print("ERROR: No suitable UTxO for registry lock.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(reg_addr, LOCK_AMOUNT, datum=reg_datum))

tx = builder.build_and_sign(signing_keys=[sk], change_address=address)
reg_hash = submit_tx(tx, label="assembly-registry")
tx_hashes.append(("Registry", reg_hash))
print(f"  TX: {reg_hash}")

print("  Waiting 10 seconds...")
time.sleep(10)

# ── Step 3: Deploy to forum ───────────────────────────────────────────────

print("\n--- [3/3] Deploying to forum validator ---")

content = b"Hello from Vector Builder Kit! This post lives on-chain."
content_hash = hashlib.sha256(content).digest()
timestamp = int(time.time())

forum_datum = RawPlutusData(cbor2.CBORTag(121, [
    bytes(pkh),
    content_hash,
    0,
    b'',
    0,
    timestamp,
]))

utxos_raw = query_utxos_ogmios(address)
funding_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 1_000_000)
if not funding_raw:
    print("ERROR: No suitable UTxO for forum lock.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(forum_addr, LOCK_AMOUNT, datum=forum_datum))

tx = builder.build_and_sign(signing_keys=[sk], change_address=address)
forum_hash = submit_tx(tx, label="assembly-forum")
tx_hashes.append(("Forum", forum_hash))
print(f"  TX: {forum_hash}")

# ── Summary ───────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("AI ASSEMBLY DEMO COMPLETE")
print(f"  3 validators tested, 3 lock transactions submitted")
print()
for name, h in tx_hashes:
    print(f"  {name:12s} TX: {h}")
print()

# Check remaining balance
utxos_raw = query_utxos_ogmios(address)
remaining = sum(u["value"]["ada"]["lovelace"] for u in utxos_raw)
spent = total_balance - remaining
print(f"  Started with: {format_ap3x(total_balance)}")
print(f"  Spent:        {format_ap3x(spent)}")
print(f"  Remaining:    {format_ap3x(remaining)}")
print()
print("Note: Unlocking requires local Ogmios + sufficient collateral.")
print("See individual deploy_*.py scripts for lock+unlock examples.")
print("=" * 60)

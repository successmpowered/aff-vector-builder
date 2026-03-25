"""
deploy_forum.py - On-chain forum post using Content-Addressed Storage

Demonstrates the CAS (Content-Addressed Storage) pattern on Vector:
1. Create forum post content and compute its SHA-256 hash
2. Store the content hash on-chain via the forum validator
3. Save the actual content to a local file (off-chain storage)

The CAS pattern: content is stored off-chain, its hash lives on-chain.
This gives you verifiable, tamper-proof content references without
bloating the blockchain with large payloads.

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
LOCK_AMOUNT = 2_000_000  # 2 AP3X

# Where to save off-chain content (CAS store)
CAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'cas_store')

# ── Load wallet and script ───────────────────────────────────────────────

print("=" * 60)
print("FORUM VALIDATOR - Content-Addressed Storage Demo")
print("=" * 60)

sk, vk, address = load_wallet(WALLET_DIR)
pkh = vk.hash()
print(f"\nWallet: {address}")

script, sh, script_address = load_script(PLUTUS_JSON, 'forum.forum.spend')
print(f"Script: {script_address}")
print(f"Hash:   {sh.payload.hex()}")

# ── Create forum post content ─────────────────────────────────────────────

content = b"Hello from Vector Builder Kit! This post lives on-chain."
content_hash = hashlib.sha256(content).digest()
timestamp = int(time.time())

print(f"\nForum post content: {content.decode()}")
print(f"Content SHA-256:    {content_hash.hex()}")
print(f"Timestamp:          {timestamp}")

# ── Query wallet UTxOs ────────────────────────────────────────────────────

ctx = VectorChainContext()
utxos_raw = query_utxos_ogmios(address)

if not utxos_raw:
    print("\nERROR: No UTxOs found. Fund your wallet first.")
    sys.exit(1)

print(f"\nWallet UTxOs:")
print_utxo_summary(utxos_raw)

# ── Lock 2 AP3X with forum post datum ─────────────────────────────────────

print("\n--- Publishing forum post on-chain ---")

# Datum: Constructor 0 with [author, content_hash, thread_id, parent_tx, post_type, timestamp]
# Fields:
#   author       - publisher's public key hash
#   content_hash - SHA-256 of the off-chain content
#   thread_id    - 0 for new thread
#   parent_tx    - empty bytes for root post
#   post_type    - 0 = original post
#   timestamp    - unix timestamp
datum = RawPlutusData(cbor2.CBORTag(121, [
    bytes(pkh),        # author
    content_hash,      # content_hash
    0,                 # thread_id (new thread)
    b'',              # parent_tx (no parent, this is root)
    0,                 # post_type (original post)
    timestamp,         # timestamp
]))

funding_utxo_raw = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + 1_000_000)
if not funding_utxo_raw:
    print("ERROR: No suitable UTxO found.")
    sys.exit(1)

funding_utxo = ogmios_utxo_to_pycardano(funding_utxo_raw, address)

builder = TransactionBuilder(ctx)
builder.add_input(funding_utxo)
builder.add_output(TransactionOutput(
    script_address,
    LOCK_AMOUNT,
    datum=datum,
))

forum_tx = builder.build_and_sign(
    signing_keys=[sk],
    change_address=address,
)

forum_tx_hash = submit_tx(forum_tx, label="forum-post")
print(f"Forum TX submitted: {forum_tx_hash}")

# ── Save content to local CAS store ──────────────────────────────────────

os.makedirs(CAS_DIR, exist_ok=True)
cas_filename = content_hash.hex() + ".txt"
cas_path = os.path.join(CAS_DIR, cas_filename)

with open(cas_path, 'wb') as f:
    f.write(content)

print(f"\nContent saved to CAS store: {cas_path}")

# Also save a metadata file linking tx hash to content
meta_path = os.path.join(CAS_DIR, content_hash.hex() + ".meta.json")
import json
metadata = {
    "tx_hash": forum_tx_hash,
    "content_hash": content_hash.hex(),
    "author": pkh.payload.hex(),
    "timestamp": timestamp,
    "content_file": cas_filename,
    "script_address": str(script_address),
}
with open(meta_path, 'w') as f:
    json.dump(metadata, f, indent=2)

print(f"Metadata saved: {meta_path}")

# ── Summary ───────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("FORUM POST PUBLISHED ON-CHAIN!")
print(f"  TX Hash:      {forum_tx_hash}")
print(f"  Content Hash: {content_hash.hex()}")
print(f"  Author:       {pkh.payload.hex()[:32]}...")
print(f"  CAS File:     {cas_filename}")
print()
print("How CAS works:")
print("  - The content hash is stored on-chain (verifiable, immutable)")
print("  - The actual content is stored off-chain (scalable, flexible)")
print("  - Anyone can verify: sha256(local_content) == on_chain_hash")
print("  - Content can be served from IPFS, S3, or any storage backend")
print("=" * 60)

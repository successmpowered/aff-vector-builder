"""
dex_demo.py - End-to-end DEX demo: place -> list -> cancel.

Demonstrates the full limit order lifecycle on Vector testnet.
Uses a single wallet, so it places an order and then cancels it
(since you cannot fill your own order).

Prerequisites:
    - Local node + Ogmios running (docker compose up)
    - Funded wallet at ../wallet (use the faucet)

Usage:
    python dex_demo.py
    python dex_demo.py --wallet ../wallet --offer 3.0
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

# Import sibling scripts
from place_order import place_order
from list_orders import list_orders, print_orders_table, PLUTUS_JSON
from cancel_order import cancel_order


DEFAULT_WALLET = os.path.join(os.path.dirname(__file__), '..', 'wallet')
WAIT_SECONDS = 10


def run_demo(wallet_dir, offer_ap3x):
    """Run the full DEX demo lifecycle."""
    print("=" * 70)
    print("  VECTOR DEX V2 - END-TO-END DEMO")
    print("=" * 70)
    print()

    # Load script address for listing
    _script, _shash, script_address = load_script(PLUTUS_JSON, "limit_order")

    # ── Step 1: Check wallet balance ─────────────────────────────────
    print("STEP 1: Checking wallet balance")
    print("-" * 40)
    sk, vk, address = load_wallet(wallet_dir)
    print(f"  Address: {address}")

    utxos_raw = query_utxos_ogmios(address)
    if not utxos_raw:
        print("ERROR: Wallet has no UTxOs. Fund it from the Vector faucet first.")
        print("  Faucet: https://faucet.vector.testnet.apexfusion.org")
        sys.exit(1)
    print_utxo_summary(utxos_raw)
    print()

    # ── Step 2: Place an order ───────────────────────────────────────
    print("STEP 2: Placing a limit order")
    print("-" * 40)
    min_receive = offer_ap3x  # Same amount (1:1 swap for demo)
    tx_hash = place_order(offer_ap3x, min_receive, wallet_dir)
    print()

    # ── Step 3: Wait for confirmation ────────────────────────────────
    print(f"STEP 3: Waiting {WAIT_SECONDS} seconds for on-chain confirmation...")
    print("-" * 40)
    for i in range(WAIT_SECONDS, 0, -1):
        print(f"  {i}...", end=" ", flush=True)
        time.sleep(1)
    print()
    print()

    # ── Step 4: List orders ──────────────────────────────────────────
    print("STEP 4: Listing open orders")
    print("-" * 40)
    orders = list_orders(str(script_address))
    print_orders_table(orders)
    print()

    # Find our order in the list
    our_order = None
    for o in orders:
        if o["tx_hash"] == tx_hash:
            our_order = o
            break

    if our_order:
        print(f"  Found our order: {our_order['order_id'][:16]}...")
    else:
        print("  WARNING: Our order not found in listing yet (may need more time).")
        print(f"  Using tx_hash from placement: {tx_hash}")
    print()

    # ── Step 5: Cancel the order ─────────────────────────────────────
    print("STEP 5: Cancelling our order (single-wallet demo)")
    print("-" * 40)
    print("  (In a real scenario, another user would fill this order.)")
    print("  (We cancel because we can't fill our own order.)")
    print()

    cancel_tx = cancel_order(tx_hash, 0, wallet_dir)
    print()

    # ── Summary ──────────────────────────────────────────────────────
    print("=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
    print()
    print(f"  Place tx:  {tx_hash}")
    print(f"  Cancel tx: {cancel_tx}")
    print(f"  Offer:     {offer_ap3x} AP3X")
    print(f"  Wallet:    {address}")
    print()
    print("  The full lifecycle worked: place -> list -> cancel")
    print("  To test fills, use two separate wallets.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Vector DEX end-to-end demo")
    parser.add_argument("--wallet", default=DEFAULT_WALLET, help="Path to wallet keys directory")
    parser.add_argument("--offer", type=float, default=3.0, help="AP3X amount to offer (default: 3.0)")
    args = parser.parse_args()

    run_demo(args.wallet, args.offer)


if __name__ == "__main__":
    main()

"""
02 - Send AP3X

Transfer AP3X to another address on Vector testnet.
Requires a local node with Ogmios running at localhost:1732.

Builds the transaction manually with TransactionBody for maximum
reliability (TransactionBuilder auto-select has known issues).

Usage:
    python 02_send_ap3x.py --to addr1... --amount 2.0
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from helpers import *

import argparse


FEE = 300_000  # 0.3 AP3X -- conservative, well above typical ~170k


def main():
    parser = argparse.ArgumentParser(description="Send AP3X on Vector testnet")
    parser.add_argument("--to", required=True, help="Destination address (addr1...)")
    parser.add_argument("--amount", required=True, type=float, help="Amount in AP3X (e.g. 2.0)")
    args = parser.parse_args()

    amount_lovelace = int(args.amount * LOVELACE_PER_AP3X)

    if amount_lovelace < MIN_UTXO:
        print(f"ERROR: Minimum send is {MIN_UTXO / LOVELACE_PER_AP3X} AP3X ({MIN_UTXO} lovelace)")
        sys.exit(1)

    to_address = Address.from_primitive(args.to)

    # Load wallet
    wallet_dir = os.path.join(os.path.dirname(__file__), '..', 'wallet')
    try:
        sk, vk, address = load_wallet(wallet_dir)
    except Exception as e:
        print(f"ERROR: Could not load wallet: {e}")
        sys.exit(1)

    print(f"From:   {address}")
    print(f"To:     {to_address}")
    print(f"Amount: {format_ap3x(amount_lovelace)}")
    print(f"Fee:    {format_ap3x(FEE)}")
    print()

    # Query UTxOs via Ogmios (needs local node)
    print("Querying UTxOs via Ogmios...")
    try:
        utxos_raw = query_utxos_ogmios(address)
    except Exception as e:
        print(f"ERROR: Could not reach Ogmios at {OGMIOS_URL}")
        print(f"  {e}")
        print("Make sure your local node and Ogmios are running.")
        sys.exit(1)

    if not utxos_raw:
        print("ERROR: No UTxOs found. Wallet is empty.")
        sys.exit(1)

    print_utxo_summary(utxos_raw)
    print()

    # Select the best pure UTxO
    utxo = best_pure_utxo(utxos_raw, min_val=amount_lovelace + FEE)
    if utxo is None:
        total = sum(u["value"]["ada"]["lovelace"] for u in utxos_raw)
        print(f"ERROR: No single UTxO has enough funds.")
        print(f"  Need: {format_ap3x(amount_lovelace + FEE)}")
        print(f"  Total balance: {format_ap3x(total)}")
        sys.exit(1)

    input_lovelace = utxo["value"]["ada"]["lovelace"]
    change_lovelace = input_lovelace - amount_lovelace - FEE

    if change_lovelace < 0:
        print(f"ERROR: Selected UTxO too small ({format_ap3x(input_lovelace)})")
        sys.exit(1)

    print(f"Selected UTxO: {utxo['transaction']['id'][:16]}...#{utxo['index']}")
    print(f"  Input:  {format_ap3x(input_lovelace)}")
    print(f"  Send:   {format_ap3x(amount_lovelace)}")
    print(f"  Fee:    {format_ap3x(FEE)}")
    print(f"  Change: {format_ap3x(change_lovelace)}")
    print()

    # Build transaction manually
    tx_in = TransactionInput(
        TransactionId(bytes.fromhex(utxo["transaction"]["id"])),
        utxo["index"],
    )

    outputs = [
        TransactionOutput(to_address, amount_lovelace),
    ]

    # Only add change output if above dust threshold
    if change_lovelace >= MIN_UTXO:
        outputs.append(TransactionOutput(address, change_lovelace))
    elif change_lovelace > 0:
        # Change too small for its own UTxO -- add it to the send amount
        print(f"NOTE: Change ({format_ap3x(change_lovelace)}) below min UTxO, adding to send amount.")
        outputs = [TransactionOutput(to_address, amount_lovelace + change_lovelace)]

    # Get current slot for TTL (valid for ~10 minutes)
    try:
        tip_slot = get_tip()
        ttl = tip_slot + 600
    except Exception:
        ttl = None  # If we can't get tip, skip TTL

    tx_body = TransactionBody(
        inputs=[tx_in],
        outputs=outputs,
        fee=FEE,
        ttl=ttl,
    )

    # Sign
    signature = sk.sign(tx_body.hash())
    vk_witness = VerificationKeyWitness(vk, signature)
    witness_set = TransactionWitnessSet(vkey_witnesses=[vk_witness])
    signed_tx = Transaction(tx_body, witness_set)

    print(f"Transaction size: {len(signed_tx.to_cbor())} bytes")
    print("Submitting...")

    # Submit via Ogmios
    try:
        tx_hash = submit_tx(signed_tx, label="send-ap3x")
    except Exception as e:
        print(f"ERROR: Submission failed: {e}")
        sys.exit(1)

    print(f"SUCCESS! Tx hash: {tx_hash}")
    print(f"Sent {args.amount} AP3X to {args.to[:20]}...")


if __name__ == "__main__":
    main()

"""
cancel_order.py - Cancel an existing limit order on the Vector DEX.

Owner-only cancellation: spends the order UTxO using the Cancel redeemer
and returns the locked funds to the owner's wallet. The transaction must
be signed by the owner's key (required_signers).

Usage:
    python cancel_order.py --tx-hash abc123... --tx-index 0
    python cancel_order.py --tx-hash abc123... --wallet ../wallet
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import cbor2


PLUTUS_JSON = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'plutus.json')
DEFAULT_WALLET = os.path.join(os.path.dirname(__file__), '..', 'wallet')


def cancel_order(tx_hash, tx_index, wallet_dir):
    """Cancel an existing limit order (owner only)."""
    print("Loading DEX contract...")
    dex_script, script_shash, script_address = load_script(PLUTUS_JSON, "limit_order")
    print(f"  Script address: {script_address}")

    print(f"Loading wallet from {wallet_dir}...")
    sk, vk, address = load_wallet(wallet_dir)
    owner_pkh = bytes(vk.hash())
    print(f"  Wallet address: {address}")
    print(f"  Owner PKH: {owner_pkh.hex()}")

    # Import the lookup function from fill_order
    from fill_order import find_order_utxo, decode_order_datum_from_ogmios

    print(f"\nLooking up order UTxO: {tx_hash[:16]}...#{tx_index}")
    order_utxo_raw = find_order_utxo(tx_hash, tx_index)
    if not order_utxo_raw:
        print("ERROR: Order UTxO not found. It may have been filled or cancelled already.")
        sys.exit(1)

    order_lovelace = order_utxo_raw["value"]["ada"]["lovelace"]
    print(f"  Found order with {format_ap3x(order_lovelace)}")

    # Decode the datum to verify ownership
    print("Decoding order datum...")
    order_data = decode_order_datum_from_ogmios(order_utxo_raw)
    datum_owner = order_data["owner_pkh"]

    if datum_owner != owner_pkh:
        print(f"ERROR: You are not the owner of this order.")
        print(f"  Order owner: {datum_owner.hex()}")
        print(f"  Your PKH:    {owner_pkh.hex()}")
        sys.exit(1)
    print(f"  Ownership verified.")

    # Query wallet UTxOs for collateral
    print("\nQuerying wallet UTxOs...")
    ctx = VectorChainContext()
    wallet_utxos = ctx.utxos(str(address))
    if not wallet_utxos:
        print("ERROR: No UTxOs in wallet (need at least one for collateral).")
        sys.exit(1)
    print(f"  Found {len(wallet_utxos)} UTxO(s)")

    # Build the order UTxO as PyCardano object
    order_tx_id = TransactionId(bytes.fromhex(tx_hash))
    order_tx_in = TransactionInput(order_tx_id, tx_index)

    datum_raw = RawPlutusData(cbor2.loads(order_data["datum_cbor"]))
    order_tx_out = TransactionOutput(
        Address.from_primitive(str(script_address)),
        order_lovelace,
        datum=datum_raw,
    )
    order_utxo = UTxO(order_tx_in, order_tx_out)

    # Cancel redeemer: Constructor 2 (CBORTag 123), no fields
    cancel_redeemer = Redeemer(
        RawPlutusData(cbor2.CBORTag(123, [])),
        ExecutionUnits(14_000_000, 10_000_000_000),  # Budget placeholder
    )

    # Build transaction
    print("\nBuilding cancel transaction...")
    builder = TransactionBuilder(ctx)

    # Add the script input with Cancel redeemer
    builder.add_script_input(
        order_utxo,
        script=dex_script,
        redeemer=cancel_redeemer,
    )

    # Add a wallet UTxO for fees and collateral
    for utxo in wallet_utxos:
        builder.add_input(utxo)

    # Set collateral
    builder.collaterals = [wallet_utxos[0]]

    # Required signers: the owner must sign to authorize cancellation
    builder.required_signers = [owner_pkh]

    # Set validity interval
    tip_slot = get_tip()
    builder.validity_start = tip_slot
    builder.ttl = tip_slot + 600  # Valid for ~10 minutes

    # Build and sign
    try:
        signed_tx = builder.build_and_sign(
            signing_keys=[sk],
            change_address=address,
        )
    except Exception as e:
        print(f"ERROR building transaction: {e}")
        sys.exit(1)

    print(f"Transaction size: {len(signed_tx.to_cbor())} bytes")

    # Submit
    print("Submitting cancel transaction via Ogmios...")
    try:
        result = submit_tx(signed_tx, label="cancel-order")
        print(f"\nSUCCESS! Order cancelled.")
        print(f"  Tx hash: {result}")
        print(f"  Returned: {format_ap3x(order_lovelace)} to {address}")
        return result
    except Exception as e:
        print(f"\nERROR submitting transaction: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Cancel a limit order on Vector DEX (owner only)")
    parser.add_argument("--tx-hash", required=True, help="Transaction hash of the order UTxO")
    parser.add_argument("--tx-index", type=int, default=0, help="Output index of the order UTxO (default: 0)")
    parser.add_argument("--wallet", default=DEFAULT_WALLET, help="Path to wallet keys directory")
    args = parser.parse_args()

    cancel_order(args.tx_hash, args.tx_index, args.wallet)


if __name__ == "__main__":
    main()

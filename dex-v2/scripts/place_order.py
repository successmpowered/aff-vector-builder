"""
place_order.py - Place a limit order on the Vector DEX.

Builds a transaction that locks AP3X at the DEX script address with
an inline LimitOrderDatum. Requires a running local node + Ogmios
for UTxO queries and transaction submission.

Usage:
    python place_order.py --offer 3.0 --min-receive 3.0
    python place_order.py --offer 5.0 --min-receive 4.5 --wallet ../wallet
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
FEE = 300_000  # Fixed fee estimate in lovelace
SCOOPER_FEE = 500_000  # 0.5 AP3X


def build_limit_order_datum(owner_pkh_bytes, offer_lovelace, min_receive_lovelace, order_id_bytes):
    """Build a LimitOrderDatum as RawPlutusData.

    Constructor 0 (CBORTag 121):
        [owner, offer_token, ask_token, min_receive, original_offer,
         scooper_fee, order_id, deadline]
    """
    token_ada = cbor2.CBORTag(121, [b'', b''])  # TokenId for AP3X

    datum = RawPlutusData(cbor2.CBORTag(121, [
        owner_pkh_bytes,       # owner: VerificationKeyHash (28 bytes)
        token_ada,             # offer_token: TokenId (AP3X)
        token_ada,             # ask_token: TokenId (AP3X)
        min_receive_lovelace,  # min_receive: Int
        offer_lovelace,        # original_offer: Int
        SCOOPER_FEE,           # scooper_fee: Int (0.5 AP3X)
        order_id_bytes,        # order_id: ByteArray (32 bytes)
        0,                     # deadline: Int (0 = no deadline)
    ]))
    return datum


def place_order(offer_ap3x, min_receive_ap3x, wallet_dir):
    """Place a limit order on the DEX."""
    offer_lovelace = int(offer_ap3x * LOVELACE_PER_AP3X)
    min_receive_lovelace = int(min_receive_ap3x * LOVELACE_PER_AP3X)

    print("Loading DEX contract...")
    _script, script_shash, script_address = load_script(PLUTUS_JSON, "limit_order")
    print(f"  Script address: {script_address}")

    print(f"Loading wallet from {wallet_dir}...")
    sk, vk, address = load_wallet(wallet_dir)
    owner_pkh = bytes(vk.hash())
    print(f"  Wallet address: {address}")
    print(f"  Owner PKH: {owner_pkh.hex()}")

    print("Querying wallet UTxOs via Ogmios...")
    utxos_raw = query_utxos_ogmios(address)
    if not utxos_raw:
        print("ERROR: No UTxOs found. Fund this wallet first.")
        sys.exit(1)
    print_utxo_summary(utxos_raw)

    # Pick the best input UTxO
    best = best_pure_utxo(utxos_raw, min_val=offer_lovelace + FEE + MIN_UTXO)
    if not best:
        print(f"ERROR: No UTxO with enough funds. Need at least {format_ap3x(offer_lovelace + FEE + MIN_UTXO)}")
        sys.exit(1)

    input_lovelace = best["value"]["ada"]["lovelace"]
    tx_id_in = TransactionId(bytes.fromhex(best["transaction"]["id"]))
    tx_in = TransactionInput(tx_id_in, best["index"])

    # Generate random 32-byte order ID
    order_id_bytes = os.urandom(32)
    print(f"\nOrder details:")
    print(f"  Order ID: {order_id_bytes.hex()[:16]}...")
    print(f"  Offer: {format_ap3x(offer_lovelace)}")
    print(f"  Min receive: {format_ap3x(min_receive_lovelace)}")
    print(f"  Scooper fee: {format_ap3x(SCOOPER_FEE)}")

    # Build datum
    datum = build_limit_order_datum(owner_pkh, offer_lovelace, min_receive_lovelace, order_id_bytes)

    # Build transaction manually
    # Output 0: locked funds at script address with inline datum
    script_output = TransactionOutput(
        Address.from_primitive(str(script_address)),
        offer_lovelace,
        datum=datum,
    )

    # Output 1: change back to wallet
    change_lovelace = input_lovelace - offer_lovelace - FEE
    if change_lovelace < MIN_UTXO:
        print(f"ERROR: Change too small ({change_lovelace}). Increase input or reduce offer.")
        sys.exit(1)

    change_output = TransactionOutput(
        Address.from_primitive(str(address)),
        change_lovelace,
    )

    tx_body = TransactionBody(
        inputs=[tx_in],
        outputs=[script_output, change_output],
        fee=FEE,
    )

    # Sign
    signature = sk.sign(tx_body.hash())
    witness = TransactionWitnessSet(vkey_witnesses=[VerificationKeyWitness(vk, signature)])
    signed_tx = Transaction(tx_body, witness)

    print(f"\nTransaction size: {len(signed_tx.to_cbor())} bytes")
    print(f"Fee: {format_ap3x(FEE)}")

    # Submit
    print("Submitting transaction via Ogmios...")
    try:
        result = submit_tx(signed_tx, label="place-order")
        print(f"\nSUCCESS! Transaction submitted.")
        print(f"  Tx hash: {result}")
        print(f"  Order ID: {order_id_bytes.hex()[:16]}...")
        print(f"  Locked: {format_ap3x(offer_lovelace)} at {script_address}")
        return result
    except Exception as e:
        print(f"\nERROR submitting transaction: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Place a limit order on Vector DEX")
    parser.add_argument("--offer", type=float, required=True, help="AP3X amount to offer (e.g. 3.0)")
    parser.add_argument("--min-receive", type=float, required=True, help="Minimum AP3X to receive (e.g. 3.0)")
    parser.add_argument("--wallet", default=DEFAULT_WALLET, help="Path to wallet keys directory")
    args = parser.parse_args()

    if args.offer <= 0 or args.min_receive <= 0:
        print("ERROR: Offer and min-receive must be positive.")
        sys.exit(1)

    place_order(args.offer, args.min_receive, args.wallet)


if __name__ == "__main__":
    main()

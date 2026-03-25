"""
fill_order.py - Fill an existing limit order on the Vector DEX.

Spends a UTxO at the DEX script address using the Fill redeemer,
paying the order owner at least min_receive. Requires a local
node + Ogmios for UTxO queries, script evaluation, and submission.

Usage:
    python fill_order.py --tx-hash abc123... --tx-index 0
    python fill_order.py --tx-hash abc123... --wallet ../wallet
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


def decode_order_datum_from_ogmios(utxo_raw):
    """Extract and decode a LimitOrderDatum from an Ogmios UTxO.

    Returns (datum_obj, decoded_fields) or raises on failure.
    """
    datum_hex = utxo_raw.get("datum")
    if not datum_hex:
        raise ValueError("UTxO has no inline datum. Is this a limit order?")

    raw_bytes = bytes.fromhex(datum_hex)
    decoded = cbor2.loads(raw_bytes)

    if not isinstance(decoded, cbor2.CBORTag) or decoded.tag != 121:
        raise ValueError(f"Unexpected datum tag: {decoded.tag if isinstance(decoded, cbor2.CBORTag) else type(decoded)}")

    fields = decoded.value
    if len(fields) < 8:
        raise ValueError(f"Datum has {len(fields)} fields, expected 8")

    return {
        "owner_pkh": fields[0],
        "min_receive": int(fields[3]),
        "original_offer": int(fields[4]),
        "scooper_fee": int(fields[5]),
        "order_id": fields[6],
        "datum_cbor": raw_bytes,
    }


def find_order_utxo(tx_hash, tx_index, ogmios_url=OGMIOS_URL):
    """Find a specific UTxO by tx hash and index via Ogmios.

    Queries the script address UTxOs and searches for the match.
    """
    # Load the script to get the address
    _script, _shash, script_address = load_script(PLUTUS_JSON, "limit_order")

    payload = {
        "jsonrpc": "2.0",
        "method": "queryLedgerState/utxo",
        "params": {"addresses": [str(script_address)]},
        "id": 1,
    }
    r = requests.post(ogmios_url, json=payload, timeout=30)
    result = r.json().get("result", [])

    for u in result:
        if u["transaction"]["id"] == tx_hash and u["index"] == tx_index:
            return u

    return None


def fill_order(tx_hash, tx_index, wallet_dir):
    """Fill an existing limit order."""
    print("Loading DEX contract...")
    dex_script, script_shash, script_address = load_script(PLUTUS_JSON, "limit_order")
    print(f"  Script address: {script_address}")

    print(f"Loading wallet from {wallet_dir}...")
    sk, vk, address = load_wallet(wallet_dir)
    filler_pkh = bytes(vk.hash())
    print(f"  Filler address: {address}")

    print(f"\nLooking up order UTxO: {tx_hash[:16]}...#{tx_index}")
    order_utxo_raw = find_order_utxo(tx_hash, tx_index)
    if not order_utxo_raw:
        print("ERROR: Order UTxO not found. It may have been filled or cancelled.")
        sys.exit(1)

    order_lovelace = order_utxo_raw["value"]["ada"]["lovelace"]
    print(f"  Found order with {format_ap3x(order_lovelace)}")

    # Decode the datum
    print("Decoding order datum...")
    order_data = decode_order_datum_from_ogmios(order_utxo_raw)
    owner_pkh = order_data["owner_pkh"]
    min_receive = order_data["min_receive"]
    print(f"  Owner: {owner_pkh.hex()[:16]}...")
    print(f"  Min receive: {format_ap3x(min_receive)}")
    print(f"  Original offer: {format_ap3x(order_data['original_offer'])}")

    # Query filler's UTxOs
    print("\nQuerying filler wallet UTxOs...")
    ctx = VectorChainContext()
    filler_utxos = ctx.utxos(str(address))
    if not filler_utxos:
        print("ERROR: No UTxOs in filler wallet.")
        sys.exit(1)
    print(f"  Found {len(filler_utxos)} UTxO(s)")

    # Build the order UTxO as a PyCardano object
    order_tx_id = TransactionId(bytes.fromhex(tx_hash))
    order_tx_in = TransactionInput(order_tx_id, tx_index)

    # Reconstruct the UTxO output with datum
    datum_raw = RawPlutusData(cbor2.loads(order_data["datum_cbor"]))
    order_tx_out = TransactionOutput(
        Address.from_primitive(str(script_address)),
        order_lovelace,
        datum=datum_raw,
    )
    order_utxo = UTxO(order_tx_in, order_tx_out)

    # Build Fill redeemer: Constructor 0, output_index=0
    fill_redeemer = Redeemer(
        RawPlutusData(cbor2.CBORTag(121, [0])),
        ExecutionUnits(14_000_000, 10_000_000_000),  # Budget placeholder, will be evaluated
    )

    # Owner address for payment
    owner_address = Address(payment_part=owner_pkh, network=NETWORK)

    # Build transaction
    print("\nBuilding fill transaction...")
    builder = TransactionBuilder(ctx)

    # Add the script input
    builder.add_script_input(
        order_utxo,
        script=dex_script,
        redeemer=fill_redeemer,
    )

    # Add filler's UTxOs as regular inputs
    for utxo in filler_utxos:
        builder.add_input(utxo)

    # Pay the order owner at least min_receive
    builder.add_output(TransactionOutput(owner_address, min_receive))

    # Set collateral from filler's wallet
    collateral_utxo = filler_utxos[0]
    builder.collaterals = [collateral_utxo]

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
    print("Submitting fill transaction via Ogmios...")
    try:
        result = submit_tx(signed_tx, label="fill-order")
        print(f"\nSUCCESS! Order filled.")
        print(f"  Tx hash: {result}")
        print(f"  Paid owner: {format_ap3x(min_receive)}")
        print(f"  Collected: {format_ap3x(order_lovelace)} from order")
        return result
    except Exception as e:
        print(f"\nERROR submitting transaction: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Fill a limit order on Vector DEX")
    parser.add_argument("--tx-hash", required=True, help="Transaction hash of the order UTxO")
    parser.add_argument("--tx-index", type=int, default=0, help="Output index of the order UTxO (default: 0)")
    parser.add_argument("--wallet", default=DEFAULT_WALLET, help="Path to wallet keys directory")
    args = parser.parse_args()

    fill_order(args.tx_hash, args.tx_index, args.wallet)


if __name__ == "__main__":
    main()

"""
list_orders.py - Query and display open limit orders on the Vector DEX.

Works without a local node by querying the public Koios API for UTxOs
at the DEX script address. Decodes each inline datum as a LimitOrderDatum
and prints a summary table.

Usage:
    python list_orders.py
    python list_orders.py --address addr1...
"""

import sys
import os
import argparse
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import cbor2
import requests


PLUTUS_JSON = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'plutus.json')


def decode_limit_order_datum(datum_cbor_hex):
    """Decode a LimitOrderDatum from CBOR hex.

    Returns a dict with the decoded fields, or None if decoding fails.
    The datum is Constructor 0 (CBORTag 121):
        [owner, offer_token, ask_token, min_receive, original_offer,
         scooper_fee, order_id, deadline]
    """
    try:
        raw = bytes.fromhex(datum_cbor_hex)
        decoded = cbor2.loads(raw)

        if not isinstance(decoded, cbor2.CBORTag) or decoded.tag != 121:
            return None

        fields = decoded.value
        if len(fields) < 8:
            return None

        owner_pkh = fields[0].hex() if isinstance(fields[0], bytes) else str(fields[0])

        # TokenId is CBORTag(121, [policy_bytes, name_bytes])
        def decode_token_id(tag):
            if isinstance(tag, cbor2.CBORTag) and tag.tag == 121:
                policy = tag.value[0].hex() if tag.value[0] else ""
                name = tag.value[1].hex() if tag.value[1] else ""
                if not policy and not name:
                    return "AP3X"
                return f"{policy[:8]}../{name}" if policy else name
            return "unknown"

        offer_token = decode_token_id(fields[1])
        ask_token = decode_token_id(fields[2])
        min_receive = int(fields[3])
        original_offer = int(fields[4])
        scooper_fee = int(fields[5])
        order_id = fields[6].hex() if isinstance(fields[6], bytes) else str(fields[6])
        deadline = int(fields[7])

        return {
            "owner": owner_pkh,
            "offer_token": offer_token,
            "ask_token": ask_token,
            "min_receive": min_receive,
            "original_offer": original_offer,
            "scooper_fee": scooper_fee,
            "order_id": order_id,
            "deadline": deadline,
        }
    except Exception as e:
        return None


def query_script_utxos_koios(script_address):
    """Query all UTxOs at a script address via Koios."""
    r = requests.post(
        f"{KOIOS_URL}/address_utxos",
        json={"_addresses": [str(script_address)]},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def list_orders(script_address):
    """Fetch and decode all limit orders at the script address."""
    print(f"Querying UTxOs at: {script_address}")
    print(f"Using Koios: {KOIOS_URL}")
    print()

    utxos = query_script_utxos_koios(script_address)
    print(f"Found {len(utxos)} UTxO(s) at script address.")

    if not utxos:
        print("No orders found.")
        return []

    orders = []
    for u in utxos:
        datum_hex = u.get("inline_datum", {}).get("bytes") if isinstance(u.get("inline_datum"), dict) else None

        # Try the raw datum bytes field if available
        if not datum_hex and u.get("datum_hash"):
            continue  # Can't decode without inline datum

        # Some Koios responses put the datum in a different format
        if not datum_hex:
            # Try to extract from inline_datum value via CBOR encoding
            inline = u.get("inline_datum")
            if inline and isinstance(inline, dict) and "value" in inline:
                # Koios sometimes returns the datum as a JSON object
                # We'll skip these for now - only process raw CBOR
                continue
            elif inline and isinstance(inline, str):
                datum_hex = inline
            else:
                continue

        decoded = decode_limit_order_datum(datum_hex)
        if decoded:
            decoded["tx_hash"] = u["tx_hash"]
            decoded["tx_index"] = u["tx_index"]
            decoded["value"] = int(u["value"])
            orders.append(decoded)

    return orders


def print_orders_table(orders):
    """Print orders as a formatted table."""
    if not orders:
        print("\nNo decodable limit orders found.")
        return

    print(f"\n{'='*90}")
    print(f"  {'Order ID':<10} {'Offer':<18} {'Min Receive':<18} {'Owner':<14} {'Tx Hash':<18}")
    print(f"{'='*90}")

    for o in orders:
        order_id = o["order_id"][:8] + "..."
        offer = format_ap3x(o["original_offer"])
        min_recv = format_ap3x(o["min_receive"])
        owner = o["owner"][:12] + "..."
        tx_hash = o["tx_hash"][:16] + "..."

        print(f"  {order_id:<10} {offer:<18} {min_recv:<18} {owner:<14} {tx_hash:<18}")

    print(f"{'='*90}")
    print(f"  Total: {len(orders)} order(s)")


def main():
    parser = argparse.ArgumentParser(description="List open limit orders on Vector DEX")
    parser.add_argument("--address", help="Override DEX script address (default: derived from plutus.json)")
    args = parser.parse_args()

    if args.address:
        script_address = args.address
        print(f"Using provided address: {script_address}")
    else:
        print("Loading DEX contract from plutus.json...")
        _script, _shash, script_address = load_script(PLUTUS_JSON, "limit_order")
        script_address = str(script_address)
        print(f"DEX script address: {script_address}")

    orders = list_orders(script_address)
    print_orders_table(orders)


if __name__ == "__main__":
    main()

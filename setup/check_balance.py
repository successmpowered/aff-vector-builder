"""
Vector Builder Kit - Check Balance

Queries the Vector testnet Koios API to show UTxO balance for an address.
No local node required.

Usage:
    python check_balance.py --address addr1v905s0u7h6a4cpyrmewyf2pkdyuxr55jjjdx556g8ce2exq64ln2s
    python check_balance.py   (loads address from ../wallet/payment.vkey)
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

import requests
from pycardano import PaymentSigningKey, PaymentVerificationKey, Address, Network

KOIOS_URL = "https://koios.vector.testnet.apexfusion.org/api/v1"
NETWORK = Network.MAINNET
LOVELACE_PER_AP3X = 1_000_000


def load_address_from_wallet():
    """Try to load address from the default wallet directory."""
    wallet_dir = os.path.join(os.path.dirname(__file__), "..", "wallet")
    skey_path = os.path.join(wallet_dir, "payment.skey")
    vkey_path = os.path.join(wallet_dir, "payment.vkey")

    if os.path.exists(skey_path):
        sk = PaymentSigningKey.load(skey_path)
        vk = PaymentVerificationKey.from_signing_key(sk)
        return str(Address(vk.hash(), network=NETWORK))
    elif os.path.exists(vkey_path):
        vk = PaymentVerificationKey.load(vkey_path)
        return str(Address(vk.hash(), network=NETWORK))

    return None


def query_utxos(address):
    """Query UTxOs for an address via Koios API."""
    r = requests.post(
        f"{KOIOS_URL}/address_utxos",
        json={"_addresses": [address]},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser(
        description="Check Vector testnet balance via Koios API"
    )
    parser.add_argument(
        "--address", "-a",
        help="Vector address to check (default: load from ../wallet/)",
    )
    args = parser.parse_args()

    address = args.address
    if not address:
        address = load_address_from_wallet()
        if not address:
            print("No address provided and no wallet found at ../wallet/")
            print("Usage: python check_balance.py --address <addr1...>")
            print("   Or: python generate_wallet.py  (to create a wallet first)")
            return 1

    print("=" * 60)
    print("  Vector Testnet Balance Check")
    print("=" * 60)
    print(f"\n  Address: {address}\n")

    try:
        utxos = query_utxos(address)
    except requests.exceptions.RequestException as e:
        print(f"  Error querying Koios API: {e}")
        return 1

    if not utxos:
        print("  No UTxOs found (balance: 0)")
        print("\n  Send test AP3X from the Vector faucet to fund this address.")
        return 0

    total_lovelace = 0
    print(f"  UTxOs: {len(utxos)}")
    print("-" * 60)

    for i, utxo in enumerate(utxos):
        tx_hash = utxo.get("tx_hash", "?")
        tx_index = utxo.get("tx_index", "?")
        value = int(utxo.get("value", 0))
        total_lovelace += value

        ap3x = value / LOVELACE_PER_AP3X
        short_hash = tx_hash[:20] + "..."
        print(f"  [{i}] {short_hash}#{tx_index}  {value:>15,} lovelace ({ap3x:,.2f} AP3X)")

        # Show any native assets on this UTxO
        asset_list = utxo.get("asset_list", [])
        if asset_list:
            for asset in asset_list:
                policy = asset.get("policy_id", "?")[:16] + "..."
                name = bytes.fromhex(asset.get("asset_name", "")).decode("utf-8", errors="replace")
                qty = asset.get("quantity", "?")
                print(f"        + {name} ({policy}): {qty}")

    print("-" * 60)
    total_ap3x = total_lovelace / LOVELACE_PER_AP3X
    print(f"  Total: {total_lovelace:,} lovelace ({total_ap3x:,.2f} AP3X)")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
01 - Check Balance

Read-only balance check using the public Koios API.
No local node required -- works with just an internet connection.

Usage:
    python 01_check_balance.py                     # uses wallet in ../wallet/
    python 01_check_balance.py --address addr1...  # check any address
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from helpers import *

import argparse


def main():
    parser = argparse.ArgumentParser(description="Check AP3X balance on Vector testnet")
    parser.add_argument("--address", type=str, help="Address to check (default: load from ../wallet/)")
    args = parser.parse_args()

    # Resolve the address
    if args.address:
        address = Address.from_primitive(args.address)
        print(f"Checking supplied address...")
    else:
        wallet_dir = os.path.join(os.path.dirname(__file__), '..', 'wallet')
        try:
            _sk, _vk, address = load_wallet(wallet_dir)
        except Exception as e:
            print(f"ERROR: Could not load wallet from {os.path.abspath(wallet_dir)}")
            print(f"  {e}")
            print(f"\nEither place payment.skey in {os.path.abspath(wallet_dir)}/")
            print(f"or pass --address addr1...")
            sys.exit(1)

    print(f"Address: {address}")
    print(f"Network: Vector Testnet (addr1 prefix)")
    print(f"Koios:   {KOIOS_URL}")
    print()

    # Query balance via Koios (read-only, no node needed)
    try:
        utxo_count, total_lovelace = query_balance_koios(address)
    except Exception as e:
        print(f"ERROR: Koios query failed: {e}")
        print("Check your internet connection or try again later.")
        sys.exit(1)

    ap3x = total_lovelace / LOVELACE_PER_AP3X

    print(f"UTxO count: {utxo_count}")
    print(f"Balance:    {format_ap3x(total_lovelace)}")
    print()

    if total_lovelace == 0:
        print("Wallet is empty. Request testnet AP3X from the Apex Fusion faucet.")
    elif utxo_count == 1:
        print("Single UTxO -- ready to transact.")
    else:
        print(f"{utxo_count} UTxOs available.")


if __name__ == "__main__":
    main()

"""
Vector Builder Kit - Generate Wallet

Creates a new Vector testnet wallet with payment keys and address.
Keys are saved to ../wallet/ relative to this script.

Usage:
    python generate_wallet.py
    python generate_wallet.py --output-dir /path/to/keys

Vector uses addr1 prefix (Network.MAINNET in PyCardano).
The native coin is AP3X (1 AP3X = 1,000,000 lovelace).
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from pycardano import PaymentSigningKey, PaymentVerificationKey, Address, Network

NETWORK = Network.MAINNET  # Vector uses addr1 prefix


def main():
    parser = argparse.ArgumentParser(
        description="Generate a new Vector testnet wallet"
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "wallet"),
        help="Directory to save keys (default: ../wallet/)",
    )
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    skey_path = os.path.join(output_dir, "payment.skey")
    vkey_path = os.path.join(output_dir, "payment.vkey")

    # Check for existing keys
    if os.path.exists(skey_path):
        print(f"Wallet already exists at {output_dir}")
        print("Delete existing keys first if you want to generate a new wallet.")
        # Show the existing address
        sk = PaymentSigningKey.load(skey_path)
        vk = PaymentVerificationKey.from_signing_key(sk)
        address = Address(vk.hash(), network=NETWORK)
        print(f"\nExisting address: {address}")
        return 0

    # Generate new keys
    sk = PaymentSigningKey.generate()
    vk = PaymentVerificationKey.from_signing_key(sk)
    address = Address(vk.hash(), network=NETWORK)

    # Save keys
    sk.save(skey_path)
    vk.save(vkey_path)

    print("=" * 60)
    print("  Vector Wallet Generated")
    print("=" * 60)
    print()
    print(f"  Keys saved to: {output_dir}")
    print(f"    payment.skey  (signing key - KEEP SECRET)")
    print(f"    payment.vkey  (verification key)")
    print()
    print(f"  Address: {address}")
    print()
    print("  Next steps:")
    print("  1. Send test AP3X to this address from the Vector faucet")
    print("  2. Run check_balance.py to verify funds arrived")
    print("  3. Start building with the examples/ scripts")
    print()
    print("  IMPORTANT: Back up your payment.skey - it controls your funds.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

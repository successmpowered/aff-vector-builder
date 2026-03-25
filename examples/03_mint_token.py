"""
03 - Mint Native Token

Mint a native token on Vector testnet using a simple ScriptPubkey policy.
The minting policy allows the wallet owner to mint freely.
Requires a local node with Ogmios running at localhost:1732.

Usage:
    python 03_mint_token.py                                  # mint 1000 VectorTestToken
    python 03_mint_token.py --name MyToken --amount 500      # mint 500 MyToken
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import argparse
from pycardano import NativeScript, ScriptPubkey, AssetName, Asset, MultiAsset, ScriptAll


def main():
    parser = argparse.ArgumentParser(description="Mint a native token on Vector testnet")
    parser.add_argument("--name", type=str, default="VectorTestToken", help="Token name (default: VectorTestToken)")
    parser.add_argument("--amount", type=int, default=1000, help="Amount to mint (default: 1000)")
    args = parser.parse_args()

    if args.amount <= 0:
        print("ERROR: Amount must be positive.")
        sys.exit(1)

    # Load wallet
    wallet_dir = os.path.join(os.path.dirname(__file__), '..', 'wallet')
    try:
        sk, vk, address = load_wallet(wallet_dir)
    except Exception as e:
        print(f"ERROR: Could not load wallet: {e}")
        sys.exit(1)

    print(f"Wallet:  {address}")
    print(f"Token:   {args.name}")
    print(f"Amount:  {args.amount}")
    print()

    # Create minting policy (ScriptPubkey: wallet owner can mint)
    pub_key_policy = ScriptPubkey(vk.hash())
    policy_script = NativeScript(pub_key_policy)
    policy_id = policy_script.hash()

    print(f"Policy ID: {policy_id}")
    print()

    # Build the mint using TransactionBuilder + VectorChainContext
    print("Connecting to Vector chain context...")
    try:
        ctx = VectorChainContext()
    except Exception as e:
        print(f"ERROR: Could not create chain context: {e}")
        sys.exit(1)

    # Query UTxOs via Ogmios for manual input selection
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

    # Select input UTxO (need enough for fee + min UTxO for token output)
    utxo = best_pure_utxo(utxos_raw, min_val=MIN_UTXO + 500_000)
    if utxo is None:
        print("ERROR: No suitable UTxO found. Need at least 2.5 AP3X in a single UTxO.")
        sys.exit(1)

    # Convert to PyCardano UTxO
    pycardano_utxo = ogmios_utxo_to_pycardano(utxo, address)

    # Build the minting asset
    asset_name = AssetName(args.name.encode("utf-8"))
    mint_asset = MultiAsset.from_primitive({policy_id.payload: {asset_name.payload: args.amount}})

    # Build transaction with TransactionBuilder
    print("Building mint transaction...")
    builder = TransactionBuilder(ctx)
    builder.add_input(pycardano_utxo)

    # Mint directive
    builder.mint = mint_asset
    builder.native_scripts = [policy_script]

    # Output: send minted tokens to ourselves (with min UTxO for token bundle)
    token_output = TransactionOutput(
        address,
        Value(MIN_UTXO, mint_asset),
    )
    builder.add_output(token_output)

    # Build and sign
    try:
        signed_tx = builder.build_and_sign(
            signing_keys=[sk],
            change_address=address,
        )
    except Exception as e:
        print(f"ERROR: Failed to build transaction: {e}")
        sys.exit(1)

    print(f"Transaction size: {len(signed_tx.to_cbor())} bytes")
    print("Submitting...")

    # Submit
    try:
        tx_hash = submit_tx(signed_tx, label="mint-token")
    except Exception as e:
        print(f"ERROR: Submission failed: {e}")
        sys.exit(1)

    print()
    print("SUCCESS!")
    print(f"  Tx hash:   {tx_hash}")
    print(f"  Policy ID: {policy_id}")
    print(f"  Token:     {args.name}")
    print(f"  Minted:    {args.amount}")
    print()
    print("The tokens will appear in your wallet after the next block (~7 seconds).")


if __name__ == "__main__":
    main()

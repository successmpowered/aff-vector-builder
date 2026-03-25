"""
04 - Lock and Unlock Funds in a PlutusV3 Script

Demonstrates the full smart contract lifecycle on Vector testnet:
1. LOCK: Send 2 AP3X to a script address with a datum
2. UNLOCK: Spend the locked UTxO by providing a redeemer

Loads the treasury validator from the ai-assembly contracts.
Requires a local node with Ogmios running at localhost:1732.

Usage:
    python 04_lock_and_unlock.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from helpers import *
from vector_chain_context import VectorChainContext

import cbor2
import time


LOCK_AMOUNT = 2_000_000  # 2 AP3X
FEE = 300_000            # 0.3 AP3X conservative fee
WAIT_SECONDS = 10        # Wait for lock tx confirmation


def lock_funds(sk, vk, address, script_address, utxos_raw):
    """Lock 2 AP3X at the script address with treasury TFunds datum."""

    print("=== LOCK PHASE ===")
    print(f"Script address: {script_address}")
    print(f"Lock amount:    {format_ap3x(LOCK_AMOUNT)}")
    print()

    # Select input UTxO
    utxo = best_pure_utxo(utxos_raw, min_val=LOCK_AMOUNT + FEE + MIN_UTXO)
    if utxo is None:
        print("ERROR: No UTxO with enough funds to lock 2 AP3X + fee + change.")
        total = sum(u["value"]["ada"]["lovelace"] for u in utxos_raw)
        print(f"  Need: {format_ap3x(LOCK_AMOUNT + FEE + MIN_UTXO)}")
        print(f"  Total balance: {format_ap3x(total)}")
        sys.exit(1)

    input_lovelace = utxo["value"]["ada"]["lovelace"]
    change_lovelace = input_lovelace - LOCK_AMOUNT - FEE

    print(f"Selected UTxO: {utxo['transaction']['id'][:16]}...#{utxo['index']}")
    print(f"  Input:  {format_ap3x(input_lovelace)}")
    print(f"  Lock:   {format_ap3x(LOCK_AMOUNT)}")
    print(f"  Fee:    {format_ap3x(FEE)}")
    print(f"  Change: {format_ap3x(change_lovelace)}")
    print()

    # Build lock transaction manually
    tx_in = TransactionInput(
        TransactionId(bytes.fromhex(utxo["transaction"]["id"])),
        utxo["index"],
    )

    # Script output with inline datum (TFunds = Constructor 1)
    datum = RawPlutusData(cbor2.CBORTag(122, []))
    script_output = TransactionOutput(
        script_address,
        LOCK_AMOUNT,
        datum=datum,
    )

    outputs = [script_output]
    if change_lovelace >= MIN_UTXO:
        outputs.append(TransactionOutput(address, change_lovelace))

    # Get TTL
    try:
        tip_slot = get_tip()
        ttl = tip_slot + 600
    except Exception:
        ttl = None

    tx_body = TransactionBody(
        inputs=[tx_in],
        outputs=outputs,
        fee=FEE,
        ttl=ttl,
    )

    # Sign and submit
    signature = sk.sign(tx_body.hash())
    vk_witness = VerificationKeyWitness(vk, signature)
    witness_set = TransactionWitnessSet(vkey_witnesses=[vk_witness])
    signed_tx = Transaction(tx_body, witness_set)

    print(f"Lock tx size: {len(signed_tx.to_cbor())} bytes")
    print("Submitting lock transaction...")

    try:
        tx_hash = submit_tx(signed_tx, label="lock-funds")
    except Exception as e:
        print(f"ERROR: Lock submission failed: {e}")
        sys.exit(1)

    print(f"Lock tx hash: {tx_hash}")
    return tx_hash


def unlock_funds(sk, vk, address, script, script_hash_val, script_address, lock_tx_hash, ctx):
    """Unlock the funds from the script address."""

    print()
    print("=== UNLOCK PHASE ===")
    print()

    # Query script address UTxOs via Ogmios
    print(f"Querying script address for locked UTxO...")
    try:
        script_utxos_raw = query_utxos_ogmios(script_address)
    except Exception as e:
        print(f"ERROR: Could not query script UTxOs: {e}")
        sys.exit(1)

    if not script_utxos_raw:
        print("ERROR: No UTxOs found at script address.")
        print("The lock transaction may not have confirmed yet. Try again in a few seconds.")
        sys.exit(1)

    # Find our locked UTxO
    locked_utxo_raw = None
    for u in script_utxos_raw:
        if u["transaction"]["id"] == lock_tx_hash:
            locked_utxo_raw = u
            break

    if locked_utxo_raw is None:
        print(f"ERROR: Could not find UTxO from lock tx {lock_tx_hash[:16]}...")
        print(f"  Found {len(script_utxos_raw)} UTxOs at script address, but none match.")
        sys.exit(1)

    locked_lovelace = locked_utxo_raw["value"]["ada"]["lovelace"]
    print(f"Found locked UTxO: {lock_tx_hash[:16]}...#{locked_utxo_raw['index']}")
    print(f"  Value: {format_ap3x(locked_lovelace)}")
    print()

    # Convert locked UTxO to PyCardano format (with datum)
    locked_tx_in = TransactionInput(
        TransactionId(bytes.fromhex(locked_utxo_raw["transaction"]["id"])),
        locked_utxo_raw["index"],
    )
    locked_tx_out = TransactionOutput(
        script_address,
        locked_lovelace,
        datum=RawPlutusData(cbor2.CBORTag(122, [])),
    )
    locked_utxo = UTxO(locked_tx_in, locked_tx_out)

    # Get a wallet UTxO for collateral
    print("Querying wallet for collateral UTxO...")
    wallet_utxos_raw = query_utxos_ogmios(address)
    collateral_raw = best_pure_utxo(wallet_utxos_raw, min_val=MIN_UTXO)
    if collateral_raw is None:
        print("ERROR: No suitable collateral UTxO in wallet.")
        sys.exit(1)

    collateral_utxo = ogmios_utxo_to_pycardano(collateral_raw, address)
    print(f"Collateral UTxO: {collateral_raw['transaction']['id'][:16]}...#{collateral_raw['index']}")
    print()

    # Build unlock transaction with TransactionBuilder
    print("Building unlock transaction...")
    redeemer = Redeemer(RawPlutusData(0), ExecutionUnits(2_000_000, 1_000_000_000))

    builder = TransactionBuilder(ctx)

    # Add the script input with redeemer
    builder.add_script_input(
        locked_utxo,
        script=script,
        datum=RawPlutusData(cbor2.CBORTag(122, [])),
        redeemer=redeemer,
    )

    # Add a wallet UTxO for fees (pick one that isn't the collateral if possible)
    fee_utxo_raw = None
    for u in wallet_utxos_raw:
        uid = f"{u['transaction']['id']}#{u['index']}"
        cid = f"{collateral_raw['transaction']['id']}#{collateral_raw['index']}"
        if uid != cid:
            val = u["value"]["ada"]["lovelace"]
            has_tokens = any(k != "ada" for k in u["value"])
            if val >= MIN_UTXO and not has_tokens:
                fee_utxo_raw = u
                break

    if fee_utxo_raw is not None:
        fee_utxo = ogmios_utxo_to_pycardano(fee_utxo_raw, address)
        builder.add_input(fee_utxo)
    else:
        # Use collateral UTxO also as fee input (allowed)
        builder.add_input(collateral_utxo)

    builder.collaterals = [collateral_utxo]

    # Build and sign
    try:
        signed_tx = builder.build_and_sign(
            signing_keys=[sk],
            change_address=address,
        )
    except Exception as e:
        print(f"ERROR: Failed to build unlock transaction: {e}")
        print("This may happen if the script execution budget is insufficient.")
        sys.exit(1)

    print(f"Unlock tx size: {len(signed_tx.to_cbor())} bytes")
    print(f"Redeemer budget: mem={redeemer.ex_units.mem:,} steps={redeemer.ex_units.steps:,}")
    print("Submitting unlock transaction...")

    try:
        tx_hash = submit_tx(signed_tx, label="unlock-funds")
    except Exception as e:
        print(f"ERROR: Unlock submission failed: {e}")
        sys.exit(1)

    return tx_hash


def main():
    print("Vector Builder Kit - Lock & Unlock PlutusV3 Script")
    print("=" * 55)
    print()

    # Load wallet
    wallet_dir = os.path.join(os.path.dirname(__file__), '..', 'wallet')
    try:
        sk, vk, address = load_wallet(wallet_dir)
    except Exception as e:
        print(f"ERROR: Could not load wallet: {e}")
        sys.exit(1)

    print(f"Wallet: {address}")
    print()

    # Load the PlutusV3 validator from ai-assembly
    plutus_json = os.path.join(os.path.dirname(__file__), '..', 'ai-assembly', 'contracts', 'plutus.json')
    try:
        script, script_hash_val, script_address = load_script(plutus_json, "treasury.treasury.spend")
    except FileNotFoundError:
        print(f"ERROR: Contract not found at {os.path.abspath(plutus_json)}")
        print("Make sure the ai-assembly contracts are compiled.")
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Validator:       treasury")
    print(f"Script hash:     {script_hash_val}")
    print(f"Script address:  {script_address}")
    print(f"Script size:     {len(script.to_primitive())} bytes")
    print()

    # Create chain context
    try:
        ctx = VectorChainContext()
    except Exception as e:
        print(f"ERROR: Could not create chain context: {e}")
        sys.exit(1)

    # Query wallet UTxOs
    print("Querying wallet UTxOs via Ogmios...")
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

    # Phase 1: Lock
    lock_tx_hash = lock_funds(sk, vk, address, script_address, utxos_raw)

    # Wait for lock to confirm
    print()
    print(f"Waiting {WAIT_SECONDS} seconds for lock tx to confirm...")
    for i in range(WAIT_SECONDS, 0, -1):
        print(f"  {i}...", end="\r")
        time.sleep(1)
    print(f"  Done.   ")
    print()

    # Phase 2: Unlock
    unlock_tx_hash = unlock_funds(sk, vk, address, script, script_hash_val, script_address, lock_tx_hash, ctx)

    print()
    print("=" * 55)
    print("SUCCESS! Full lock-and-unlock cycle complete.")
    print(f"  Lock tx:   {lock_tx_hash}")
    print(f"  Unlock tx: {unlock_tx_hash}")
    print(f"  Funds returned to wallet: {address}")


if __name__ == "__main__":
    main()

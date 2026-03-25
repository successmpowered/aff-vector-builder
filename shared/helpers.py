"""
Vector Builder Kit - Shared Helpers

Common functions used by all scripts in the kit.
Import this from any script with:

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
    from helpers import *
"""

import os
import sys
import json
import time
import hashlib
import requests
from pathlib import Path

from pycardano import (
    PaymentSigningKey,
    PaymentVerificationKey,
    Address,
    Network,
    TransactionBuilder,
    TransactionBody,
    TransactionOutput,
    TransactionInput,
    TransactionId,
    TransactionWitnessSet,
    Transaction,
    VerificationKeyWitness,
    Value,
    MultiAsset,
    UTxO,
    PlutusV3Script,
    Redeemer,
    RawPlutusData,
    ExecutionUnits,
    script_hash,
)

# ── Network Constants ──────────────────────────────────────────────────────

KOIOS_URL = "https://koios.vector.testnet.apexfusion.org/api/v1"
OGMIOS_URL = "http://localhost:1732"
NETWORK = Network.MAINNET  # Vector uses addr1 prefix
LOVELACE_PER_AP3X = 1_000_000
MIN_UTXO = 2_000_000  # 2 AP3X minimum per UTxO


# ── Wallet Functions ───────────────────────────────────────────────────────

def generate_wallet(keys_dir):
    """Generate a new wallet. Returns (sk, vk, address)."""
    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)

    sk = PaymentSigningKey.generate()
    vk = PaymentVerificationKey.from_signing_key(sk)
    address = Address(vk.hash(), network=NETWORK)

    sk.save(str(keys_dir / "payment.skey"))
    vk.save(str(keys_dir / "payment.vkey"))

    return sk, vk, address


def load_wallet(keys_dir):
    """Load wallet from keys directory. Returns (sk, vk, address).
    Generates new wallet if keys don't exist."""
    keys_dir = Path(keys_dir)
    sk_path = keys_dir / "payment.skey"

    if not sk_path.exists():
        print(f"No wallet found at {keys_dir}. Generating new wallet...")
        return generate_wallet(keys_dir)

    sk = PaymentSigningKey.load(str(sk_path))
    vk = PaymentVerificationKey.from_signing_key(sk)
    address = Address(vk.hash(), network=NETWORK)
    return sk, vk, address


# ── Balance & UTxO Queries ─────────────────────────────────────────────────

def query_balance_koios(address):
    """Query balance via public Koios API (no local node needed).
    Returns (utxo_count, total_lovelace)."""
    addr_str = str(address)
    r = requests.post(
        f"{KOIOS_URL}/address_utxos",
        json={"_addresses": [addr_str]},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    utxos = r.json()

    total = sum(int(u["value"]) for u in utxos)
    return len(utxos), total


def query_utxos_ogmios(address, ogmios_url=OGMIOS_URL):
    """Query UTxOs via local Ogmios (up-to-date with node tip).
    Returns raw Ogmios response list."""
    r = requests.post(
        ogmios_url,
        json={
            "jsonrpc": "2.0",
            "method": "queryLedgerState/utxo",
            "params": {"addresses": [str(address)]},
            "id": 1,
        },
        timeout=30,
    )
    return r.json().get("result", [])


def get_tip(ogmios_url=OGMIOS_URL):
    """Get current chain tip slot from Ogmios."""
    r = requests.post(
        ogmios_url,
        json={"jsonrpc": "2.0", "method": "queryLedgerState/tip", "params": {}, "id": 1},
        timeout=30,
    )
    return r.json()["result"]["slot"]


# ── UTxO Selection ─────────────────────────────────────────────────────────

def best_pure_utxo(utxos_raw, min_val=MIN_UTXO):
    """Select the best spendable UTxO from Ogmios raw results.
    Picks the largest pure-lovelace UTxO without datum or tokens."""
    candidates = []
    for u in utxos_raw:
        val = u["value"]["ada"]["lovelace"]
        has_tokens = any(k != "ada" for k in u["value"])
        has_datum = "datum" in u or "datumHash" in u
        if val >= min_val and not has_datum and not has_tokens:
            candidates.append(u)
    candidates.sort(key=lambda u: u["value"]["ada"]["lovelace"], reverse=True)
    return candidates[0] if candidates else None


def ogmios_utxo_to_pycardano(raw, address):
    """Convert an Ogmios raw UTxO to a PyCardano UTxO object."""
    tx_id = TransactionId(bytes.fromhex(raw["transaction"]["id"]))
    tx_in = TransactionInput(tx_id, raw["index"])
    lovelace = raw["value"]["ada"]["lovelace"]
    tx_out = TransactionOutput(Address.from_primitive(str(address)), lovelace)
    return UTxO(tx_in, tx_out)


# ── Transaction Submission ─────────────────────────────────────────────────

def submit_tx(signed_tx_or_cbor, ogmios_url=OGMIOS_URL, label=""):
    """Submit a signed transaction via Ogmios.
    Accepts a Transaction object or CBOR hex string.
    Returns tx hash on success, raises on failure."""
    if isinstance(signed_tx_or_cbor, Transaction):
        cbor_hex = signed_tx_or_cbor.to_cbor().hex()
    elif isinstance(signed_tx_or_cbor, bytes):
        cbor_hex = signed_tx_or_cbor.hex()
    else:
        cbor_hex = signed_tx_or_cbor

    r = requests.post(
        ogmios_url,
        json={
            "jsonrpc": "2.0",
            "method": "submitTransaction",
            "params": {"transaction": {"cbor": cbor_hex}},
            "id": label or None,
        },
        timeout=30,
    )
    res = r.json()

    if "error" in res:
        raise Exception(f"Submission failed: {res['error']}")

    tx_info = res.get("result", {})
    if isinstance(tx_info, dict):
        return tx_info.get("transaction", {}).get("id", "ok")
    return str(tx_info)


def wait_for_tx(tx_hash, address, ogmios_url=OGMIOS_URL, timeout=60, poll_interval=5):
    """Wait for a transaction to appear in UTxO set.
    Polls Ogmios for the address until the tx_hash appears or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        utxos = query_utxos_ogmios(address, ogmios_url)
        for u in utxos:
            if u["transaction"]["id"] == tx_hash:
                return True
        time.sleep(poll_interval)
    return False


# ── Script Loading ─────────────────────────────────────────────────────────

def load_script(plutus_json_path, title_contains):
    """Load a PlutusV3 script from a compiled plutus.json (Aiken blueprint).
    Returns (script, script_hash, script_address)."""
    with open(plutus_json_path) as f:
        bp = json.load(f)

    for v in bp["validators"]:
        if title_contains in v["title"]:
            hex_code = v["compiledCode"]
            s = PlutusV3Script(bytes.fromhex(hex_code))
            sh = script_hash(s)
            addr = Address(sh, network=NETWORK)
            return s, sh, addr

    available = [v["title"] for v in bp["validators"]]
    raise ValueError(f"No validator matching '{title_contains}' found. Available: {available}")


# ── Formatting ─────────────────────────────────────────────────────────────

def format_ap3x(lovelace):
    """Format lovelace as AP3X string."""
    ap3x = lovelace / LOVELACE_PER_AP3X
    return f"{lovelace:,} lovelace ({ap3x:,.2f} AP3X)"


def print_utxo_summary(utxos_raw):
    """Print a summary of Ogmios raw UTxOs."""
    total = sum(u["value"]["ada"]["lovelace"] for u in utxos_raw)
    print(f"  UTxOs: {len(utxos_raw)}")
    print(f"  Balance: {format_ap3x(total)}")
    for i, u in enumerate(utxos_raw[:5]):
        val = u["value"]["ada"]["lovelace"]
        txid = u["transaction"]["id"][:16]
        has_tokens = any(k != "ada" for k in u["value"])
        marker = " [has tokens]" if has_tokens else ""
        print(f"    [{i}] {txid}...#{u['index']} = {format_ap3x(val)}{marker}")
    if len(utxos_raw) > 5:
        print(f"    ... and {len(utxos_raw) - 5} more")


# ── Simple Transfer Builder ───────────────────────────────────────────────

def build_simple_transfer(sk, vk, from_address, to_address, amount_lovelace, utxos_raw):
    """Build and sign a simple AP3X transfer transaction.
    Uses manual input selection (TransactionBuilder auto-select has issues).
    Returns signed Transaction object."""
    from vector_chain_context import VectorChainContext

    ctx = VectorChainContext()
    builder = TransactionBuilder(ctx)

    # Add all UTxOs as inputs (let builder calculate change)
    for raw in utxos_raw:
        utxo = ogmios_utxo_to_pycardano(raw, from_address)
        builder.add_input(utxo)

    builder.add_output(TransactionOutput(
        Address.from_primitive(str(to_address)),
        amount_lovelace,
    ))

    signed_tx = builder.build_and_sign(
        signing_keys=[sk],
        change_address=from_address,
    )
    return signed_tx

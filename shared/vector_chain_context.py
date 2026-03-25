"""
Vector Testnet Chain Context for PyCardano

Implements the PyCardano ChainContext interface for Vector testnet.
Queries chain state via Koios (read) and Ogmios (read+write).

Key differences from Cardano mainnet:
- Uses addr1 prefix (mainnet-style addressing) but is a testnet
- Native coin is AP3X (not ADA), but protocol treats it as lovelace
- Block time ~6-7 seconds
- Protocol version 10.0 (Conway era)
"""

import json
import requests
from typing import Dict, List, Optional, Union

from pycardano import (
    ChainContext,
    ProtocolParameters,
    GenesisParameters,
    Network,
    UTxO,
    TransactionInput,
    TransactionOutput,
    TransactionId,
    Value,
    MultiAsset,
    Asset,
    AssetName,
    ScriptHash,
    Address,
    Transaction,
    ExecutionUnits,
    PlutusV1Script,
    PlutusV2Script,
    PlutusV3Script,
    NativeScript,
    Datum,
    RawPlutusData,
    DatumHash,
)

# Default endpoints
KOIOS_URL = "https://koios.vector.testnet.apexfusion.org/api/v1"
OGMIOS_URL = "https://ogmios.vector.testnet.apexfusion.org"
SUBMIT_URL = "https://submit.vector.testnet.apexfusion.org"


class VectorChainContext(ChainContext):
    """
    PyCardano ChainContext implementation for Vector testnet.

    Usage:
        ctx = VectorChainContext()
        # Use with TransactionBuilder or direct transaction building
    """

    def __init__(
        self,
        base_url: str = KOIOS_URL,
        network: Network = Network.MAINNET,  # Vector uses addr1 prefix
        ogmios_url: str = OGMIOS_URL,
        submit_url: str = SUBMIT_URL,
    ):
        super().__init__()
        self.base_url = base_url
        self._network = network
        self.ogmios_url = ogmios_url
        self.submit_url = submit_url
        self._epoch = None
        self._protocol_param = None
        self._genesis_param = None
        self._last_block_slot = None

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint}"
        r = requests.request(method, url, **kwargs)
        r.raise_for_status()
        return r.json()

    def _get(self, endpoint, **params):
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint, data):
        return self._request("POST", endpoint, json=data,
                           headers={"Content-Type": "application/json"})

    @property
    def network(self) -> Network:
        return self._network

    @property
    def epoch(self) -> int:
        if self._epoch is None:
            tip = self._get("tip")
            self._epoch = tip[0]["epoch_no"]
        return self._epoch

    @property
    def last_block_slot(self) -> int:
        tip = self._get("tip")
        self._last_block_slot = tip[0]["abs_slot"]
        return self._last_block_slot

    @property
    def genesis_param(self) -> GenesisParameters:
        if self._genesis_param is None:
            self._genesis_param = GenesisParameters(
                active_slots_coefficient=0.05,
                update_quorum=5,
                max_lovelace_supply=45000000000000000,
                network_magic=764825075,
                epoch_length=86400,
                system_start=0,
                slots_per_kes_period=129600,
                slot_length=1,
                max_kes_evolutions=62,
                security_param=2160,
            )
        return self._genesis_param

    @property
    def protocol_param(self) -> ProtocolParameters:
        if self._protocol_param is None:
            params = self._get("epoch_params")
            p = params[0]

            # Parse cost models - supports both int and string keys
            class HybridCostModels(dict):
                pass

            cost_models = HybridCostModels()
            if p.get("cost_models"):
                cm = p["cost_models"]
                if isinstance(cm, str):
                    cm = json.loads(cm)
                for version_name, version_key in [("PlutusV1", 0), ("PlutusV2", 1), ("PlutusV3", 2)]:
                    if version_name in cm:
                        raw = cm[version_name]
                        if isinstance(raw, list):
                            cm_dict = {i: v for i, v in enumerate(raw)}
                        elif isinstance(raw, dict):
                            cm_dict = raw
                        else:
                            continue
                        cost_models[version_key] = cm_dict
                        cost_models[version_name] = cm_dict

            self._protocol_param = ProtocolParameters(
                min_fee_constant=int(p["min_fee_b"]),
                min_fee_coefficient=int(p["min_fee_a"]),
                max_block_size=int(p["max_block_size"]),
                max_tx_size=int(p["max_tx_size"]),
                max_block_header_size=int(p["max_bh_size"]),  # Koios uses max_bh_size
                key_deposit=int(p["key_deposit"]),
                pool_deposit=int(p["pool_deposit"]),
                pool_influence=(3, 10),
                monetary_expansion=(3, 1000),
                treasury_expansion=(2, 10),
                decentralization_param=0,
                extra_entropy="",
                protocol_major_version=int(p["protocol_major"]),
                protocol_minor_version=int(p["protocol_minor"]),
                min_utxo=int(p.get("min_utxo_value", 0)),
                min_pool_cost=int(p.get("min_pool_cost", 0)),
                price_mem=float(p["price_mem"]),
                price_step=float(p["price_step"]),
                max_tx_ex_mem=int(p["max_tx_ex_mem"]),
                max_tx_ex_steps=int(p["max_tx_ex_steps"]),
                max_block_ex_mem=int(p["max_block_ex_mem"]),
                max_block_ex_steps=int(p["max_block_ex_steps"]),
                max_val_size=int(p["max_val_size"]),
                collateral_percent=int(p["collateral_percent"]),
                max_collateral_inputs=int(p["max_collateral_inputs"]),
                coins_per_utxo_word=0,  # Deprecated but required by PyCardano
                coins_per_utxo_byte=int(p["coins_per_utxo_size"]),
                cost_models=cost_models,
            )
        return self._protocol_param

    def _utxos_from_ogmios(self, addr_str: str) -> List[UTxO]:
        """Fetch UTxOs from local Ogmios (always up-to-date with node tip)."""
        payload = {
            "jsonrpc": "2.0",
            "method": "queryLedgerState/utxo",
            "params": {"addresses": [addr_str]},
            "id": 1
        }
        r = requests.post(self.ogmios_url, json=payload, timeout=30)
        data = r.json()
        raw_utxos = data.get("result", [])

        result = []
        for raw in raw_utxos:
            tx_id = TransactionId.from_primitive(raw["transaction"]["id"])
            tx_idx = raw["index"]
            tx_in = TransactionInput(tx_id, tx_idx)

            lovelace = raw["value"]["ada"]["lovelace"]

            multi_asset = None
            for key, assets in raw["value"].items():
                if key == "ada":
                    continue
                if multi_asset is None:
                    multi_asset = MultiAsset()
                policy = ScriptHash.from_primitive(key)
                asset = Asset()
                for asset_name_hex, quantity in assets.items():
                    name = AssetName(bytes.fromhex(asset_name_hex) if asset_name_hex else b"")
                    asset[name] = quantity
                multi_asset[policy] = asset

            if multi_asset:
                value = Value(lovelace, multi_asset)
            else:
                value = lovelace

            tx_out = TransactionOutput(Address.from_primitive(addr_str), value)
            result.append(UTxO(tx_in, tx_out))

        return result

    def _utxos_from_koios(self, addr_str: str) -> List[UTxO]:
        """Fetch UTxOs from Koios API (may lag a few seconds behind tip)."""
        raw_utxos = self._post("address_utxos", {"_addresses": [addr_str]})

        result = []
        for raw in raw_utxos:
            tx_id = TransactionId.from_primitive(raw["tx_hash"])
            tx_idx = raw["tx_index"]
            tx_in = TransactionInput(tx_id, tx_idx)

            lovelace = int(raw["value"])

            multi_asset = None
            if raw.get("asset_list"):
                multi_asset = MultiAsset()
                for asset in raw["asset_list"]:
                    policy = ScriptHash.from_primitive(asset["policy_id"])
                    name = AssetName(bytes.fromhex(asset["asset_name"]))
                    quantity = int(asset["quantity"])
                    if policy not in multi_asset:
                        multi_asset[policy] = {}
                    multi_asset[policy][name] = quantity

            if multi_asset:
                value = Value(lovelace, multi_asset)
            else:
                value = lovelace

            datum = None
            datum_hash = None
            if raw.get("inline_datum"):
                try:
                    datum = RawPlutusData.from_dict(raw["inline_datum"]["value"])
                except Exception:
                    pass
            if raw.get("datum_hash"):
                datum_hash = DatumHash.from_primitive(raw["datum_hash"])

            tx_out = TransactionOutput(
                Address.from_primitive(addr_str), value,
                datum_hash=datum_hash, datum=datum,
            )
            result.append(UTxO(tx_in, tx_out))

        return result

    def utxos(self, address: Union[str, Address]) -> List[UTxO]:
        """Fetch UTxOs. Uses Ogmios if available, falls back to Koios."""
        addr_str = str(address)
        try:
            return self._utxos_from_ogmios(addr_str)
        except Exception:
            return self._utxos_from_koios(addr_str)

    def submit_tx_cbor(self, cbor: Union[bytes, str]):
        """Submit a signed transaction.

        Uses the dedicated submit REST endpoint (submit_url) if set,
        otherwise falls back to Ogmios JSON-RPC.
        """
        if isinstance(cbor, bytes):
            cbor_bytes = cbor
            cbor_hex = cbor.hex()
        else:
            cbor_hex = cbor
            cbor_bytes = bytes.fromhex(cbor)

        if self.submit_url:
            # Standard Cardano submit REST API: POST raw CBOR with application/cbor
            r = requests.post(
                f"{self.submit_url}/api/submit/tx",
                data=cbor_bytes,
                headers={"Content-Type": "application/cbor"},
                timeout=30,
            )
            if r.status_code not in (200, 202):
                raise Exception(f"Transaction submission failed: {r.status_code} {r.text}")
            return r.text or "submitted"

        # Fallback: Ogmios JSON-RPC submitTransaction
        payload = {
            "jsonrpc": "2.0",
            "method": "submitTransaction",
            "params": {"transaction": {"cbor": cbor_hex}},
            "id": None
        }
        r = requests.post(self.ogmios_url, json=payload, timeout=30)
        result = r.json()

        if "error" in result:
            raise Exception(f"Transaction submission failed: {result['error']}")
        return result.get("result", result)

    def evaluate_tx_cbor(self, cbor: Union[bytes, str]) -> Dict[str, ExecutionUnits]:
        """Evaluate execution units for a Plutus transaction via Ogmios."""
        if isinstance(cbor, bytes):
            cbor_hex = cbor.hex()
        else:
            cbor_hex = cbor

        payload = {
            "jsonrpc": "2.0",
            "method": "evaluateTransaction",
            "params": {"transaction": {"cbor": cbor_hex}},
            "id": None
        }
        r = requests.post(self.ogmios_url, json=payload, timeout=30)
        result = r.json()

        if "error" in result:
            raise Exception(f"Transaction evaluation failed: {result['error']}")

        budget = result.get("result", [])
        exec_units = {}
        for item in budget:
            key = f"{item.get('validator', {}).get('purpose', 'unknown')}:{item.get('validator', {}).get('index', 0)}"
            exec_units[key] = ExecutionUnits(
                item.get("budget", {}).get("memory", 0),
                item.get("budget", {}).get("cpu", 0),
            )
        return exec_units


if __name__ == "__main__":
    ctx = VectorChainContext()
    print("Vector Chain Context - Connection Test")
    print(f"  Network: {ctx.network}")
    print(f"  Epoch: {ctx.epoch}")
    print(f"  Last slot: {ctx.last_block_slot}")
    print(f"  Protocol: v{ctx.protocol_param.protocol_major_version}.{ctx.protocol_param.protocol_minor_version}")
    print("  Status: READY")

# AI Assembly

**On-chain governance system built with 5 PlutusV3 validators on Vector.**

AI Assembly is a complete governance stack deployed on Vector (the UTXO L2 in the Apex Fusion ecosystem). Five smart contracts work together to provide member registration, proposal creation, voting, discussion, and treasury management -- all on-chain.

Every contract is written in Aiken, compiled to PlutusV3, and deployable to Vector testnet with the included Python scripts.

---

## The Governance Stack

| Validator | Purpose |
|-----------|---------|
| **council** | Council membership management and voting power |
| **registry** | Member registration (stake-to-register pattern) |
| **governance** | Proposal creation and vote tallying |
| **forum** | On-chain discussion with Content-Addressed Storage |
| **treasury** | Controlled fund disbursement after governance approval |

These five contracts work together: members register via `registry`, discuss via `forum`, propose changes via `governance`, council members vote via `council`, and approved proposals trigger `treasury` disbursements.

---

## Getting Started

### Prerequisites

- Python 3.9+ with PyCardano 0.19.2 (`pip install pycardano cbor2 requests`)
- A funded Vector testnet wallet in `../wallet/` (payment.skey + payment.vkey)
- Local Ogmios at `localhost:1732` connected to a synced Vector node

### Running the Scripts

Each script is standalone and can be run directly:

```bash
# Lock and unlock from treasury
python scripts/deploy_escrow.py

# Council validator demo (governance seats)
python scripts/deploy_multisig.py

# Governance lifecycle (register + propose)
python scripts/deploy_governance.py

# Forum post with Content-Addressed Storage
python scripts/deploy_forum.py

# End-to-end multi-validator demo (treasury + registry + forum)
python scripts/assembly_demo.py
```

The `assembly_demo.py` script runs through three validators in sequence and requires at least 10 AP3X in your wallet.

---

## Content-Addressed Storage (CAS)

The forum validator demonstrates the CAS pattern, which solves the "large data on-chain" problem:

**On-chain (immutable, verifiable):**
- SHA-256 hash of the content
- Author's public key hash
- Thread ID, parent reference, timestamp

**Off-chain (scalable, flexible):**
- The actual content (text, images, documents)
- Stored locally in `cas_store/`, but could be IPFS, S3, Arweave, etc.

**Verification:** Anyone can check `sha256(off_chain_content) == on_chain_hash` to prove the content hasn't been tampered with. The blockchain acts as a timestamped notary.

This pattern is how you build social networks, content platforms, and document systems on UTXO chains without bloating every block with megabytes of data.

---

## Frontend Dashboard

A browser-based dashboard is included for visualizing deployed contracts and interacting with validators.

```
Open: frontend/index.html
```

The frontend connects to Koios for read queries and displays contract state, UTxO maps, and transaction history.

---

## Documentation

Detailed documentation lives in the `docs/` directory:

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, validator interactions, data flow |
| [CONTRACT_PATTERNS.md](docs/CONTRACT_PATTERNS.md) | Deep dive into contract patterns |
| [AGENT_GUIDE.md](docs/AGENT_GUIDE.md) | How AI agents can build and submit transactions |
| [FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md) | Building your own frontend for AI Assembly |

---

## Contract Source Code

All 5 Aiken source files are in `contracts/source/`:

```
contracts/source/council.ak
contracts/source/registry.ak
contracts/source/governance.ak
contracts/source/forum.ak
contracts/source/treasury.ak
contracts/source/types.ak     (shared types)
```

The compiled PlutusV3 bytecode is in `contracts/plutus.json` (Aiken blueprint format).

# Vector Builder Kit

> Build on Vector - Apex Fusion's UTXO Layer 2

## What's Inside

- **DEX V2** -- Permissionless order book DEX with 3 PlutusV3 validators
- **AI Assembly** -- 30 smart contract patterns proving UTXO can do everything EVM does
- Pre-compiled contracts, Python scripts, static frontends, Docker node setup

## What is Vector?

Vector is a UTXO-based Layer 2 in the Apex Fusion ecosystem. It runs Cardano's protocol (PlutusV3, Conway era) with ~6 second block times. The native coin is AP3X.

## Prerequisites

- Python 3.9 or newer -- <https://python.org>
- Docker Desktop (optional, needed for transaction submission) -- <https://docker.com>
- Any modern web browser

## Quick Start

**Step 1: Install dependencies**

```
cd vector-builder-kit
pip install -r shared/requirements.txt
```

**Step 2: Check your setup**

```
python setup/check_prerequisites.py
```

**Step 3: Generate a wallet**

```
python setup/generate_wallet.py
```

**Step 4: Get test AP3X**

Go to the Apex Fusion Discord and use the faucet, then check your balance:

```
python setup/check_balance.py
```

**Step 5 (Optional): Start a local node for transaction submission**

```
# Windows users first run:
python setup/fix_crlf.py

cd docker
docker compose up -d
# Wait 3-4 hours for sync
```

## Read-Only Mode (No Node Required)

These work immediately with just Python and a browser:

```
python examples/01_check_balance.py        # Check any wallet balance
python dex-v2/scripts/list_orders.py       # View open DEX orders
```

Open in your browser:

- `dex-v2/frontend/index.html` -- DEX dashboard
- `ai-assembly/frontend/index.html` -- AI Assembly dashboard

## Full Mode (Requires Local Node)

After the node is synced:

```
python examples/02_send_ap3x.py --to <addr> --amount 2   # Transfer AP3X
python examples/03_mint_token.py                          # Mint a native token
python examples/04_lock_and_unlock.py                     # Lock/unlock with PlutusV3
python dex-v2/scripts/dex_demo.py                         # Full DEX lifecycle
python ai-assembly/scripts/assembly_demo.py               # AI Assembly demo
```

## Directory Structure

```
vector-builder-kit/
  ai-assembly/          # 30 smart contract patterns
    contracts/           # Aiken source + compiled plutus.json
    scripts/             # Python interaction scripts
    frontend/            # Static HTML dashboard
    docs/                # Pattern catalog and guides
  dex-v2/               # Order book DEX
    contracts/           # 3 PlutusV3 validators
    scripts/             # Python DEX scripts
    frontend/            # Static HTML dashboard
    docs/                # DEX documentation
  docker/               # Local node + Ogmios setup
  examples/             # Standalone example scripts
  setup/                # Wallet generation, balance check, prerequisites
  shared/               # VectorChainContext, requirements.txt, utilities
```

## Using with Claude Code (AI-Assisted Development)

The kit includes a `CLAUDE.md` file that gives Claude Code full context about Vector's architecture, PyCardano quirks, datum encoding, and the script structure. This means you can use AI to help you build, debug, and explore.

### Getting Started

1. **Download Claude Desktop** from https://claude.ai/download (free, works on Windows/Mac/Linux)
2. **Open Claude Desktop** and click the **"Code"** button (or look for Claude Code in the app)
3. **Point it to the `vector-builder-kit` folder** — just open the folder or drag it in
4. **Start asking questions** — Claude reads the `CLAUDE.md` file automatically and understands the entire project

That's it. No API keys, no terminal commands, no setup.

### What You Can Ask Claude

**Explore and learn:**
- "Explain how the DEX limit order validator works"
- "Read the treasury contract source and explain the datum fields"
- "What governance validators are in the AI Assembly?"

**Run scripts:**
- "Check my wallet balance"
- "List open orders on the DEX"
- "Run the lock and unlock example"
- "Place a 3 AP3X limit order on the DEX"

**Build new things:**
- "Write a script that places a DEX order and then cancels it after 30 seconds"
- "Create a new frontend that shows all forum posts from the AI Assembly"
- "Write a script that locks 5 AP3X in the treasury validator"
- "Modify the council script to require two signers"

**Debug issues:**
- "My transaction failed with error 3136, what went wrong?"
- "The node isn't syncing, help me troubleshoot"
- "Why is my datum being rejected by the validator?"

### How It Works

Claude Code reads `CLAUDE.md` for project context (network config, PyCardano quirks, datum encoding patterns, key files). It can read any file in the kit, run Python scripts, and help you write new ones. All the smart contract source (`.ak` files) is included so Claude can explain validator logic.

### Tips

- Start with read-only operations (no node needed): "Check balance for addr1..." or "List DEX orders"
- Claude knows about the broken TransactionBuilder auto-selection and will use manual `add_input()`
- Ask Claude to read a specific `.ak` validator source before writing interaction scripts
- If you're building a frontend, ask Claude to read `ai-assembly/docs/FRONTEND_GUIDE.md` first

## Build Your Own Frontend

Both projects include pre-compiled contracts (`plutus.json`) and static HTML frontends you can fork. See `ai-assembly/docs/FRONTEND_GUIDE.md` for a detailed guide.

## Technical Details

| Detail | Value |
|---|---|
| Network | Vector Testnet (`addr1` prefix, uses `Network.MAINNET` in PyCardano) |
| Native coin | AP3X (1 AP3X = 1,000,000 lovelace) |
| Protocol | v10.0 (Conway era, PlutusV3) |
| Koios API | `https://koios.vector.testnet.apexfusion.org/api/v1` (read-only) |
| Ogmios | `localhost:1732` (requires local node) |
| Block time | ~6-7 seconds |

## Community

Report bugs, suggest improvements, share your builds.

## License

Apache-2.0

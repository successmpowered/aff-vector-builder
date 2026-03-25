# Building a Local Frontend for The AI Assembly

## Quick Start: Static Dashboard (Already Included)

The simplest option is already in the package:

```bash
# Just open in your browser
open frontend/index.html
# or on Windows:
start frontend/index.html
```

This is a self-contained single HTML file with embedded CSS and JavaScript. No build step, no dependencies, no server required.

## Building a Live Interactive Frontend

If you want a frontend that queries the chain in real-time and lets you interact with the contracts, follow this guide.

### Option A: Vanilla HTML + JavaScript (Recommended for Simplicity)

Create a new `frontend/live.html` that connects to Ogmios for live data:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Assembly - Live Dashboard</title>
  <style>
    :root {
      --bg: #0a0a0f;
      --bg2: #12121a;
      --bg3: #1a1a2e;
      --text: #e4e4ed;
      --text-muted: #8888a0;
      --accent: #7c3aed;
      --accent2: #a78bfa;
      --green: #10b981;
      --red: #ef4444;
      --border: #2a2a3e;
      --card: #16162a;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 2rem;
    }
    h1 { font-size: 2rem; margin-bottom: 1.5rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
    }
    .card h3 { color: var(--accent2); margin-bottom: 0.5rem; }
    .stat { font-size: 2rem; font-weight: 700; color: var(--green); }
    .label { font-size: 0.85rem; color: var(--text-muted); }
    .utxo-list { margin-top: 1rem; font-size: 0.85rem; }
    .utxo-item {
      background: var(--bg3);
      border-radius: 8px;
      padding: 0.75rem;
      margin-bottom: 0.5rem;
    }
    .refresh-btn {
      background: var(--accent);
      color: white;
      border: none;
      padding: 0.75rem 1.5rem;
      border-radius: 8px;
      cursor: pointer;
      font-size: 1rem;
      margin-bottom: 1.5rem;
    }
    .refresh-btn:hover { opacity: 0.9; }
    #status { color: var(--text-muted); margin-left: 1rem; }
  </style>
</head>
<body>
  <h1>The AI Assembly - Live Dashboard</h1>
  <button class="refresh-btn" onclick="refresh()">Refresh All</button>
  <span id="status"></span>

  <div class="grid" id="validator-grid">
    <!-- Cards populated by JavaScript -->
  </div>

  <script>
    // Configuration - edit these for your setup
    const OGMIOS_URL = 'http://localhost:1732';

    // Validator addresses (from plutus.json compilation)
    // Replace these with your actual script addresses after compilation
    const VALIDATORS = {
      'Multisig': 'addr1wyqwcl0802mchmxhu4g4m39ez6w35v4gg3yxjuh5xh295ls8jqwek',
      'Escrow': '',      // Fill after aiken build
      'Treasury': '',    // Fill after aiken build
      'DEX Swap': '',    // Fill after aiken build
      'Oracle': '',      // Fill after aiken build
      // Add all 30...
    };

    async function queryUTxOs(address) {
      if (!address) return [];
      try {
        const r = await fetch(OGMIOS_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'queryLedgerState/utxo',
            params: { addresses: [address] },
            id: 1
          })
        });
        const data = await r.json();
        return data.result || [];
      } catch (e) {
        console.error(`Error querying ${address}:`, e);
        return [];
      }
    }

    function formatLovelace(l) {
      return (l / 1_000_000).toFixed(2) + ' AP3X';
    }

    async function refresh() {
      const status = document.getElementById('status');
      status.textContent = 'Refreshing...';
      const grid = document.getElementById('validator-grid');
      grid.innerHTML = '';

      for (const [name, addr] of Object.entries(VALIDATORS)) {
        const card = document.createElement('div');
        card.className = 'card';

        if (!addr) {
          card.innerHTML = `<h3>${name}</h3><p class="label">Address not configured</p>`;
          grid.appendChild(card);
          continue;
        }

        const utxos = await queryUTxOs(addr);
        const totalValue = utxos.reduce((s, u) => s + (u.value?.ada?.lovelace || 0), 0);
        const scriptUtxos = utxos.filter(u => 'datum' in u);

        let html = `<h3>${name}</h3>`;
        html += `<div class="stat">${scriptUtxos.length}</div>`;
        html += `<div class="label">Active UTxOs (${formatLovelace(totalValue)} locked)</div>`;

        if (scriptUtxos.length > 0) {
          html += '<div class="utxo-list">';
          for (const u of scriptUtxos.slice(0, 5)) {
            html += `<div class="utxo-item">`;
            html += `TX: ${u.transaction.id.slice(0, 16)}...#${u.index}<br>`;
            html += `Value: ${formatLovelace(u.value.ada.lovelace)}`;
            if (u.datum) html += `<br>Datum: ${u.datum.slice(0, 20)}...`;
            html += `</div>`;
          }
          if (scriptUtxos.length > 5) {
            html += `<div class="label">+${scriptUtxos.length - 5} more</div>`;
          }
          html += '</div>';
        }

        card.innerHTML = html;
        grid.appendChild(card);
      }

      status.textContent = `Updated at ${new Date().toLocaleTimeString()}`;
    }

    // Auto-refresh on load
    refresh();
  </script>
</body>
</html>
```

**To use this:**

1. Compile the contracts with `aiken build` to get `plutus.json`
2. Run a Python script to extract script addresses:
   ```python
   import json
   from pycardano import *

   with open("plutus.json") as f:
       bp = json.load(f)

   for v in bp["validators"]:
       if v["title"].endswith(".spend"):
           script = PlutusV3Script(bytes.fromhex(v["compiledCode"]))
           addr = Address(script_hash(script), network=Network.MAINNET)
           print(f"  '{v['title'].split('.')[0]}': '{addr}',")
   ```
3. Paste the addresses into the `VALIDATORS` object in `live.html`
4. Open `live.html` in your browser

**Important:** Your browser will need CORS access to Ogmios. If Ogmios blocks browser requests, you can either:
- Start Ogmios with CORS headers enabled
- Run a tiny proxy: `npx cors-anywhere` on port 8080, then change `OGMIOS_URL` to `http://localhost:8080/http://localhost:1732`

### Option B: React + TypeScript (For Production)

For a more robust frontend:

```bash
npx create-react-app ai-assembly-ui --template typescript
cd ai-assembly-ui
npm install lucid-cardano   # or @meshsdk/core for Cardano interaction
```

Key components to build:

1. **ValidatorCard** - Shows UTxO count, total locked value, last activity
2. **TransactionBuilder** - UI form to lock/spend with datum/redeemer inputs
3. **WalletConnect** - Connect browser wallet (Nami, Eternl, etc.)
4. **TransactionHistory** - Show recent TXs from the contract addresses
5. **ExecutionStats** - Real-time PlutusV3 execution counter

### Option C: Python Backend + HTML Frontend

If you prefer a Python-served dashboard:

```bash
pip install flask
```

```python
# app.py
from flask import Flask, jsonify, send_from_directory
import requests

app = Flask(__name__, static_folder='frontend')
OGMIOS = 'http://localhost:1732'

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/api/utxos/<address>')
def get_utxos(address):
    r = requests.post(OGMIOS, json={
        'jsonrpc': '2.0',
        'method': 'queryLedgerState/utxo',
        'params': {'addresses': [address]},
        'id': 1
    }, timeout=30)
    return jsonify(r.json().get('result', []))

@app.route('/api/submit', methods=['POST'])
def submit():
    from flask import request
    cbor = request.json.get('cbor')
    r = requests.post(OGMIOS, json={
        'jsonrpc': '2.0',
        'method': 'submitTransaction',
        'params': {'transaction': {'cbor': cbor}},
        'id': 'submit'
    }, timeout=30)
    return jsonify(r.json())

if __name__ == '__main__':
    app.run(port=3000, debug=True)
```

Then run: `python app.py` and open `http://localhost:3000`

This avoids CORS issues since the Python backend proxies Ogmios calls.

## Styling Guide

The included `frontend/index.html` uses a dark theme with these design tokens:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#0a0a0f` | Page background |
| `--bg2` | `#12121a` | Section background |
| `--card` | `#16162a` | Card background |
| `--accent` | `#7c3aed` | Primary purple |
| `--accent2` | `#a78bfa` | Light purple |
| `--green` | `#10b981` | Success states |
| `--red` | `#ef4444` | Error states |
| `--gold` | `#f59e0b` | Warnings/highlights |
| `--text` | `#e4e4ed` | Primary text |
| `--text-muted` | `#8888a0` | Secondary text |

Font: Inter (with system fallbacks)

## Data Flow

```
Browser  -->  Ogmios (localhost:1732)  -->  Vector Node  -->  Chain
   |                                           |
   |  queryLedgerState/utxo                    |
   |  <-- UTxO list (JSON)                     |
   |                                           |
   |  submitTransaction                        |
   |  <-- TX hash or error                     |
```

For read-only dashboards, you only need `queryLedgerState/utxo`. For interactive features (locking/spending), you also need wallet key management and transaction building (use PyCardano on a backend, or Lucid/MeshJS in the browser).

# Quick Start (5 Minutes)

Install dependencies:

```
cd vector-builder-kit
pip install -r shared/requirements.txt
```

Generate a wallet:

```
python setup/generate_wallet.py
```

Get test AP3X from the Apex Fusion Discord faucet, then confirm your balance:

```
python setup/check_balance.py
```

Try a read-only script:

```
python dex-v2/scripts/list_orders.py
```

Open the DEX dashboard in your browser:

```
dex-v2/frontend/index.html
```

That's it. For transaction submission, see the full [README](README.md) on setting up a local node.

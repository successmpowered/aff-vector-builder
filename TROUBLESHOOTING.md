# Troubleshooting

## Python

**Python version too old**

You need Python 3.9 or newer. Check with:

```
python --version
```

If your system default is older, try `python3` instead of `python`.

**pip install fails**

Try installing with the `--user` flag:

```
python -m pip install --user -r shared/requirements.txt
```

## Docker and Node

**Docker not running**

Start Docker Desktop before running `docker compose up -d`.

**CRLF genesis hash mismatch (Windows)**

Windows line endings cause genesis file hashes to change, which prevents the node from starting. Fix this before starting Docker:

```
python setup/fix_crlf.py
```

**Node sync takes hours**

This is normal. A full sync takes 3-4 hours. You can use read-only scripts and frontends while waiting.

**Ogmios connection refused**

Either the node is not fully synced yet, or Docker is not running. Check with `docker compose ps` in the `docker/` directory.

**Port 1732 already in use**

Another Ogmios instance may be running. Stop it or change the port in `docker-compose.yml`.

## Transactions

**Transaction submission failed**

Check that the node is fully synced. A partially synced node will reject transactions.

**Insufficient funds**

Each UTxO requires a minimum of about 2 AP3X, plus you need extra for fees. Request more from the faucet if needed.

## Addressing

**addr1 prefix confusion**

Vector uses mainnet-style addressing (`addr1` prefix) but it is a testnet. In PyCardano, use `Network.MAINNET`.

## PyCardano

**TransactionBuilder auto-selection fails**

This is a known PyCardano issue with custom chain contexts. All scripts in this kit use manual `add_input()` as a workaround.

**"coins_per_utxo_word" errors**

Already handled in VectorChainContext. If you see this in your own code, set `coins_per_utxo_word=0`.

## Node.js

**Lucid Evolution or MeshJS not working**

These libraries have a known `libsodium` ESM compatibility bug on Node.js v24+. Use the Python toolchain instead.

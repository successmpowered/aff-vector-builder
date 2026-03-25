# Vector Node - Docker Setup

Run a Vector testnet node and Ogmios gateway locally. This gives you
a transaction-submit endpoint and real-time chain queries for your scripts.

## Prerequisites

| Requirement | Link |
|---|---|
| Docker Desktop (Windows) | https://docs.docker.com/desktop/install/windows-install/ |
| Docker Desktop (Mac) | https://docs.docker.com/desktop/install/mac-install/ |
| Docker Engine (Linux) | https://docs.docker.com/engine/install/ |

Allocate at least **4 GB RAM** to Docker (Settings > Resources on Docker Desktop).

## Windows Users - Fix Line Endings First

Windows Git converts LF to CRLF on checkout. The node hashes genesis files at
startup and CRLF bytes cause hash mismatches, preventing sync past the Byron era.

Run this **before** starting the containers:

```bash
python ../setup/fix_crlf.py
```

This converts all genesis JSON files under `config/` back to Unix line endings.

## Start

```bash
docker compose up -d
```

Two containers will start:

| Service | Description | Port |
|---|---|---|
| `vector-relay` | Cardano node syncing Vector testnet | internal only |
| `ogmios` | JSON-RPC gateway (query + submit) | `localhost:1732` |

## Check Node Sync Progress

```bash
docker compose logs -f vector-relay
```

Look for lines like `Chain extended` with increasing slot numbers.
The node is fully synced when the slot number matches the current network tip.

## Check Ogmios

Once the node passes its health check (~60 seconds after start), Ogmios will
come up automatically.

```bash
curl http://localhost:1732/health
```

You can also open http://localhost:1732 in a browser to see the Ogmios dashboard.

## Expected Sync Time

A full sync from genesis takes approximately **3-4 hours** depending on your
hardware and network connection. The node processes around 27,000 blocks per
minute on typical hardware.

## Stop

```bash
docker compose down
```

This stops the containers but preserves the chain database. Next startup
will resume from where it left off.

## Reset (Remove Chain Data)

```bash
docker compose down -v
```

The `-v` flag removes the `node-db` volume, forcing a full re-sync on next start.

## Memory Notes

- The Cardano node uses approximately 2-3 GB RAM during sync.
- Ogmios adds roughly 200 MB.
- Recommended: set Docker to at least 4 GB RAM (6 GB is more comfortable).
- On machines with 8 GB total RAM, close other heavy applications during initial sync.

## Troubleshooting

**Node exits immediately**: Check `docker compose logs vector-relay`. If you
see genesis hash errors on Windows, run the CRLF fix script (see above).

**Ogmios not starting**: It waits for the node health check to pass. Give it
1-2 minutes after the node starts. Check with `docker compose ps`.

**Slow sync**: Ensure Docker has enough RAM and your disk is not full. SSD
storage significantly improves sync speed over HDD.

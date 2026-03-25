"""
Vector Builder Kit - Check Prerequisites

Verifies that your system has everything needed to work with
the Vector Builder Kit.

Usage:
    python check_prerequisites.py

Checks:
    - Python >= 3.9
    - pip available
    - Docker available (optional)
    - docker compose available (optional)
    - pycardano installed and version
    - cbor2 installed
    - requests installed
    - Vector testnet Koios API reachable
    - Local Ogmios reachable (optional)
"""

import sys
import os
import subprocess
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

KOIOS_URL = "https://koios.vector.testnet.apexfusion.org/api/v1"
OGMIOS_URL = "http://localhost:1732"

OK = "\u2705"   # green checkmark
FAIL = "\u274c"  # red X
WARN = "\u26a0\ufe0f"   # warning


def check_python():
    v = sys.version_info
    if v >= (3, 9):
        print(f"  {OK} Python {v.major}.{v.minor}.{v.micro}")
        return True
    else:
        print(f"  {FAIL} Python {v.major}.{v.minor}.{v.micro} (need >= 3.9)")
        print("     Fix: Install Python 3.9+ from https://python.org")
        return False


def check_pip():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.strip().split("\n")[0]
            print(f"  {OK} pip ({version_line.split('(')[0].strip()})")
            return True
    except Exception:
        pass
    print(f"  {FAIL} pip not available")
    print("     Fix: python -m ensurepip --upgrade")
    return False


def check_docker():
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  {OK} Docker ({version})")
            return True
    except FileNotFoundError:
        pass
    except Exception:
        pass
    print(f"  {WARN} Docker not found (optional - needed for local node)")
    print("     Install: https://docs.docker.com/get-docker/")
    return False


def check_docker_compose():
    # Try "docker compose" (v2 plugin) first, then "docker-compose" (standalone)
    for cmd in [["docker", "compose", "version"], ["docker-compose", "--version"]]:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"  {OK} docker compose ({version})")
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue
    print(f"  {WARN} docker compose not found (optional - needed for local node)")
    print("     Install: https://docs.docker.com/compose/install/")
    return False


def check_module(name, display_name=None):
    display_name = display_name or name
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", getattr(mod, "VERSION", "installed"))
        print(f"  {OK} {display_name} ({version})")
        return True
    except ImportError:
        print(f"  {FAIL} {display_name} not installed")
        print(f"     Fix: pip install {name}")
        return False


def check_koios():
    try:
        import requests
        r = requests.get(f"{KOIOS_URL}/tip", timeout=15)
        r.raise_for_status()
        tip = r.json()
        if tip and len(tip) > 0:
            slot = tip[0].get("abs_slot", "?")
            block = tip[0].get("block_no", "?")
            print(f"  {OK} Koios API reachable (tip: slot {slot}, block {block})")
            return True
    except Exception as e:
        pass
    print(f"  {FAIL} Koios API not reachable at {KOIOS_URL}")
    print("     Check your internet connection")
    return False


def check_ogmios():
    try:
        import requests
        r = requests.post(
            OGMIOS_URL,
            json={
                "jsonrpc": "2.0",
                "method": "queryLedgerState/tip",
                "params": {},
                "id": 1,
            },
            timeout=5,
        )
        res = r.json()
        if "result" in res:
            slot = res["result"].get("slot", "?")
            print(f"  {OK} Ogmios reachable at {OGMIOS_URL} (tip slot: {slot})")
            return True
    except Exception:
        pass
    print(f"  {WARN} Ogmios not reachable at {OGMIOS_URL} (optional - needed for tx submit)")
    print("     Start with: docker compose up -d (in docker/ directory)")
    return False


def main():
    print("=" * 60)
    print("  Vector Builder Kit - Prerequisites Check")
    print("=" * 60)
    print()

    required_ok = True

    print("[System]")
    required_ok &= check_python()
    required_ok &= check_pip()
    print()

    print("[Docker] (optional - for local node)")
    check_docker()
    check_docker_compose()
    print()

    print("[Python Packages]")
    required_ok &= check_module("pycardano")
    required_ok &= check_module("cbor2")
    required_ok &= check_module("requests")
    print()

    print("[Network]")
    required_ok &= check_koios()
    check_ogmios()
    print()

    print("=" * 60)
    if required_ok:
        print(f"  {OK} All required prerequisites met!")
        print("  You're ready to use the Vector Builder Kit.")
    else:
        print(f"  {FAIL} Some required prerequisites are missing.")
        print("  Fix the issues above and run this check again.")
    print("=" * 60)

    return 0 if required_ok else 1


if __name__ == "__main__":
    sys.exit(main())

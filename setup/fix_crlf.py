"""
Vector Builder Kit - Fix CRLF Line Endings

Fixes Windows CRLF (\\r\\n) line endings in Docker genesis/config files.
This is required because Docker mounts files into Linux containers, and
CRLF line endings cause genesis file hash mismatches that prevent the
Vector node from syncing.

Usage:
    python fix_crlf.py
    python fix_crlf.py --config-dir /path/to/docker/config

The script walks the config directory, finds all .json and .yaml files,
and converts CRLF to LF. Only files that actually contain CRLF are modified.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))


def fix_crlf_in_directory(config_dir):
    """Walk directory, fix CRLF in .json and .yaml files. Returns (checked, fixed) counts."""
    checked = 0
    fixed = 0
    target_extensions = {".json", ".yaml", ".yml"}

    for root, dirs, files in os.walk(config_dir):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in target_extensions:
                continue

            filepath = os.path.join(root, filename)
            checked += 1

            try:
                with open(filepath, "rb") as f:
                    data = f.read()
            except (OSError, PermissionError) as e:
                print(f"  \u274c Could not read: {filepath} ({e})")
                continue

            if b"\r\n" not in data:
                rel = os.path.relpath(filepath, config_dir)
                print(f"  \u2705 OK (LF): {rel}")
                continue

            # Count CRLF occurrences for reporting
            crlf_count = data.count(b"\r\n")
            new_data = data.replace(b"\r\n", b"\n")

            try:
                with open(filepath, "wb") as f:
                    f.write(new_data)
                rel = os.path.relpath(filepath, config_dir)
                print(f"  \U0001f527 Fixed:  {rel} ({crlf_count} CRLF -> LF)")
                fixed += 1
            except (OSError, PermissionError) as e:
                print(f"  \u274c Could not write: {filepath} ({e})")

    return checked, fixed


def main():
    parser = argparse.ArgumentParser(
        description="Fix CRLF line endings in Docker config files for Vector node"
    )
    parser.add_argument(
        "--config-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "docker", "config"),
        help="Path to Docker config directory (default: ../docker/config/)",
    )
    args = parser.parse_args()

    config_dir = os.path.abspath(args.config_dir)

    print("=" * 60)
    print("  Vector Builder Kit - Fix CRLF Line Endings")
    print("=" * 60)
    print()

    if not os.path.isdir(config_dir):
        print(f"  Config directory not found: {config_dir}")
        print("  Make sure the docker/ directory exists with config files.")
        print("  Expected path: vector-builder-kit/docker/config/")
        return 1

    print(f"  Scanning: {config_dir}")
    print()

    checked, fixed = fix_crlf_in_directory(config_dir)

    print()
    print("-" * 60)
    print(f"  Files checked: {checked}")
    print(f"  Files fixed:   {fixed}")

    if fixed > 0:
        print()
        print("  CRLF line endings were fixed. Genesis file hashes will now")
        print("  match the expected values and the Vector node should sync")
        print("  correctly in Docker.")
    elif checked > 0:
        print()
        print("  All files already have correct LF line endings.")
    else:
        print()
        print("  No .json or .yaml files found in the config directory.")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET_DIR=${TARGET_DIR:-/app/zero_trust_access}

for module in visibility.py graph.py sessions.py policy.py; do
    install -m 0644 "$SCRIPT_DIR/zero_trust_access/$module" "$TARGET_DIR/$module"
done

python3 -m py_compile "$TARGET_DIR"/*.py

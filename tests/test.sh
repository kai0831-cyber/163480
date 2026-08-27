#!/bin/bash
set -uo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOG_DIR=${VERIFIER_LOG_DIR:-/logs/verifier}
REWARD_FILE="$LOG_DIR/reward.txt"
mkdir -p "$LOG_DIR"
printf '0\n' > "$REWARD_FILE"

CANDIDATE_ROOT=${CANDIDATE_ROOT:-/app}
if grep -RInE 'sample_case\.json|integrated-inherited-scope|r-main|2026-08-25T12:00:00Z|13\.6|121\.567|r-known-correction|r-active-long-path' "$CANDIDATE_ROOT/zero_trust_access" >/dev/null 2>&1; then
    exit 1
fi

on_exit() {
    status=$?
    if [ "$status" -ne 0 ]; then
        printf '0\n' > "$REWARD_FILE"
    fi
}
trap on_exit EXIT
trap 'printf "0\n" > "$REWARD_FILE"; exit 124' HUP INT TERM

if timeout 300 python3 "$SCRIPT_DIR/test_cases.py"; then
    printf '1\n' > "$REWARD_FILE"
    exit 0
fi
exit 1

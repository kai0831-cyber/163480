#!/usr/bin/env python3
import json
import os
import sys


sys.path.insert(0, os.environ.get("CANDIDATE_ROOT", "/app"))

from zero_trust_access import evaluate_batch


try:
    payload = json.load(sys.stdin)
    result = evaluate_batch(payload)
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.write("\n")
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(2)

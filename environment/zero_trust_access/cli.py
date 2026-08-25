import json
import sys

from .engine import evaluate_batch


def main():
    try:
        result = evaluate_batch(json.load(sys.stdin))
        json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

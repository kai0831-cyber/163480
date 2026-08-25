from collections import defaultdict

from .common import timestamp


def resolve(rows, id_key, cutoff):
    grouped = defaultdict(list)
    for row in rows:
        if timestamp(row["published_at"]) <= cutoff:
            grouped[row[id_key]].append(row)
    selected = []
    for logical_id in sorted(grouped):
        winner = max(grouped[logical_id], key=lambda row: row["revision"])
        if winner["op"] == "UPSERT":
            selected.append(dict(winner))
    return selected

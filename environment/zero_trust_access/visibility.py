from collections import defaultdict

from .common import timestamp


def resolve(rows, id_key, cutoff):
    grouped = defaultdict(list)
    for row in rows:
        if timestamp(row["published_at"]) <= cutoff:
            grouped[row[id_key]].append(row)
    selected = []
    for logical_id in sorted(grouped):
        eligible = grouped[logical_id]
        winner = max(eligible, key=lambda row: (timestamp(row["published_at"]), row["revision"]))
        if winner["op"] == "RETRACT":
            prior = [row for row in eligible if row["op"] == "UPSERT"]
            if not prior:
                continue
            winner = max(prior, key=lambda row: (timestamp(row["published_at"]), row["revision"]))
        selected.append(dict(winner))
    return selected

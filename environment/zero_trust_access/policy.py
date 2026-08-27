from .common import timestamp
from .graph import effective_labels, is_in_scope, membership_paths, resource_depth


RANK = {"GROUP": 1, "ROLE": 2, "PRINCIPAL": 3}


def evaluate(request, model, policies, memberships, active_role_id):
    at = timestamp(request["evaluated_at"])
    paths = membership_paths(memberships, request["principal_id"], at)
    resource_labels = effective_labels(model["resources"], request["resource_id"])
    applicable = []
    for row in policies:
        if not (timestamp(row["valid_from"]) <= at < timestamp(row["valid_until"])):
            continue
        if not row["actions"] or request["action"] != row["actions"][0]:
            continue
        if not is_in_scope(model["resources"], row["resource_id"], request["resource_id"], row["include_descendants"]):
            continue
        if resource_labels != dict(row["required_labels"]):
            continue
        kind = row["subject_type"]
        if kind == "PRINCIPAL" and row["subject_id"] == request["principal_id"]:
            path = ()
        elif kind == "GROUP" and row["subject_id"] in paths:
            path = paths[row["subject_id"]]
        elif kind == "ROLE" and row["subject_id"] == active_role_id:
            path = ()
        else:
            continue
        score = (RANK[kind], resource_depth(model["resources"], row["resource_id"]))
        applicable.append((score, row, path))
    if not applicable:
        return "DENY", "NO_MATCH", []
    best = max(score for score, _, _ in applicable)
    governing = [(row, path) for score, row, path in applicable if score == best]
    evidence = [
        {"policy_id": row["policy_id"], "effect": row["effect"], "subject_path": list(path)}
        for row, path in sorted(governing, key=lambda item: item[0]["policy_id"])
    ]
    if any(row["effect"] == "DENY" for _, row, _ in applicable):
        return "DENY", "POLICY_DENY", evidence
    return "ALLOW", "POLICY_ALLOW", evidence

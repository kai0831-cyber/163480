from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import heapq
import json


def dt(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def select(rows, identity, cutoff):
    grouped = defaultdict(list)
    for row in rows:
        if dt(row["published_at"]) <= cutoff:
            grouped[row[identity]].append(row)
    result = []
    for logical_id in sorted(grouped):
        winner = max(grouped[logical_id], key=lambda row: row["revision"])
        if winner["op"] == "UPSERT":
            result.append(row_copy(winner))
    return result


def row_copy(row):
    return json.loads(json.dumps(row))


def paths(memberships, principal_id, at):
    starts = []
    adjacency = defaultdict(list)
    for row in memberships:
        if not (dt(row["valid_from"]) <= at < dt(row["valid_until"])):
            continue
        edge = (row["membership_id"], row["group_id"])
        if row["member_type"] == "PRINCIPAL" and row["member_id"] == principal_id:
            starts.append(edge)
        elif row["member_type"] == "GROUP":
            adjacency[row["member_id"]].append(edge)
    best = {}
    heap = []
    for membership_id, target in starts:
        heapq.heappush(heap, (1, (membership_id,), target))
    while heap:
        _, path, group_id = heapq.heappop(heap)
        old = best.get(group_id)
        if old is not None and (len(old), old) <= (len(path), path):
            continue
        best[group_id] = path
        for membership_id, target in sorted(adjacency[group_id]):
            new_path = path + (membership_id,)
            old = best.get(target)
            if old is None or (len(new_path), new_path) < (len(old), old):
                heapq.heappush(heap, (len(new_path), new_path, target))
    return best


def depth(resources, resource_id):
    result = 0
    current = resources[resource_id]["parent_id"]
    while current is not None:
        result += 1
        current = resources[current]["parent_id"]
    return result


def in_scope(resources, policy_resource, requested_resource, descendants):
    current = requested_resource
    while current is not None:
        if current == policy_resource:
            return current == requested_resource or descendants
        current = resources[current]["parent_id"]
    return False


def inherited_labels(resources, resource_id):
    lineage = []
    current = resource_id
    while current is not None:
        lineage.append(current)
        current = resources[current]["parent_id"]
    result = {}
    for item in reversed(lineage):
        result.update(resources[item]["labels"])
    return result


def sessions_from(events):
    grouped = defaultdict(list)
    for event in events:
        grouped[event["session_id"]].append(event)
    result = {}
    for session_id, rows in grouped.items():
        requests = [row for row in rows if row["kind"] == "REQUEST"]
        if len(requests) != 1:
            raise ValueError("bad session")
        result[session_id] = {
            "request": requests[0],
            "approvals": [row for row in rows if row["kind"] == "APPROVE"],
            "revocations": [row for row in rows if row["kind"] == "REVOKE"],
        }
    return result


def active(session, at, roles, memberships):
    request = session["request"]
    if not (dt(request["effective_at"]) <= at and dt(request["valid_from"]) <= at < dt(request["valid_until"])):
        return False
    if any(dt(row["effective_at"]) <= at for row in session["revocations"]):
        return False
    role = roles[request["role_id"]]
    eligible = set()
    for approval in session["approvals"]:
        approval_at = dt(approval["effective_at"])
        approver = approval["approver_id"]
        if approval_at <= at and approver != request["principal_id"]:
            if role["approver_group_id"] in paths(memberships, approver, approval_at):
                eligible.add(approver)
    return len(eligible) >= role["approval_threshold"]


def evaluate_policy(request, resources, policies, memberships, active_role):
    at = dt(request["evaluated_at"])
    subject_paths = paths(memberships, request["principal_id"], at)
    labels = inherited_labels(resources, request["resource_id"])
    rank = {"GROUP": 1, "ROLE": 2, "PRINCIPAL": 3}
    matches = []
    for policy in policies:
        if not (dt(policy["valid_from"]) <= at < dt(policy["valid_until"])):
            continue
        if request["action"] not in policy["actions"]:
            continue
        if not in_scope(resources, policy["resource_id"], request["resource_id"], policy["include_descendants"]):
            continue
        if any(labels.get(key) != value for key, value in policy["required_labels"].items()):
            continue
        kind = policy["subject_type"]
        if kind == "PRINCIPAL" and policy["subject_id"] == request["principal_id"]:
            path = ()
        elif kind == "GROUP" and policy["subject_id"] in subject_paths:
            path = subject_paths[policy["subject_id"]]
        elif kind == "ROLE" and policy["subject_id"] == active_role:
            path = ()
        else:
            continue
        matches.append(((depth(resources, policy["resource_id"]), rank[kind]), policy, path))
    if not matches:
        return "DENY", "NO_MATCH", []
    best = max(score for score, _, _ in matches)
    governing = [(policy, path) for score, policy, path in matches if score == best]
    evidence = [
        {"policy_id": policy["policy_id"], "effect": policy["effect"], "subject_path": list(path)}
        for policy, path in sorted(governing, key=lambda pair: pair[0]["policy_id"])
    ]
    if any(policy["effect"] == "DENY" for policy, _ in governing):
        return "DENY", "POLICY_DENY", evidence
    return "ALLOW", "POLICY_ALLOW", evidence


def expected(payload):
    cutoff = dt(payload["knowledge_cutoff"])
    memberships = select(payload["membership_events"], "membership_id", cutoff)
    policies = select(payload["policy_events"], "policy_id", cutoff)
    session_events = select(payload["session_events"], "session_event_id", cutoff)
    principals = {row["principal_id"]: row for row in payload["principals"]}
    roles = {row["role_id"]: row for row in payload["roles"]}
    resources = {row["resource_id"]: row for row in payload["resources"]}
    sessions = sessions_from(session_events)
    decisions = []
    for request in sorted(payload["requests"], key=lambda row: row["request_id"]):
        at = dt(request["evaluated_at"])
        session_id = request["session_id"]
        active_role = None
        if session_id is not None:
            session = sessions.get(session_id)
            if session is None or session["request"]["principal_id"] != request["principal_id"] or not active(session, at, roles, memberships):
                decisions.append(decision_row(request, "DENY", "SESSION_INVALID", [], []))
                continue
            active_role = session["request"]["role_id"]
            incompatible = set(roles[active_role]["incompatible_roles"])
            conflicts = []
            for other_id, other in sessions.items():
                if other_id != session_id and other["request"]["principal_id"] == request["principal_id"]:
                    if other["request"]["role_id"] in incompatible and active(other, at, roles, memberships):
                        conflicts.append(other_id)
            if conflicts:
                decisions.append(decision_row(request, "DENY", "SOD_CONFLICT", [], sorted(conflicts)))
                continue
        result, reason, governing = evaluate_policy(request, resources, policies, memberships, active_role)
        decisions.append(decision_row(request, result, reason, governing, []))

    tenants = sorted({row["tenant_id"] for row in principals.values()})
    totals = {tenant: {"tenant_id": tenant, "requests": 0, "allowed": 0, "denied": 0, "policy_denied": 0, "session_denied": 0, "sod_denied": 0, "no_match": 0} for tenant in tenants}
    for row in decisions:
        total = totals[principals[row["principal_id"]]["tenant_id"]]
        total["requests"] += 1
        if row["decision"] == "ALLOW":
            total["allowed"] += 1
        else:
            total["denied"] += 1
            total[{"POLICY_DENY": "policy_denied", "SESSION_INVALID": "session_denied", "SOD_CONFLICT": "sod_denied", "NO_MATCH": "no_match"}[row["reason"]]] += 1
    tenant_totals = [totals[tenant] for tenant in tenants]
    core = {"decisions": decisions, "tenant_totals": tenant_totals}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return {"as_of": payload["as_of"], "knowledge_cutoff": payload["knowledge_cutoff"], **core, "snapshot_digest": digest}


def decision_row(request, decision, reason, governing, conflicts):
    return {
        "request_id": request["request_id"], "principal_id": request["principal_id"],
        "resource_id": request["resource_id"], "action": request["action"],
        "evaluated_at": request["evaluated_at"], "decision": decision, "reason": reason,
        "governing_policies": governing, "conflicting_sessions": conflicts,
    }

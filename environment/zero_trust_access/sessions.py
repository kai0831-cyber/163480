from collections import defaultdict

from .common import timestamp
from .graph import membership_paths


def build_sessions(events):
    grouped = defaultdict(list)
    for event in events:
        grouped[event["session_id"]].append(event)
    result = {}
    for session_id, rows in grouped.items():
        requests = [row for row in rows if row["kind"] == "REQUEST"]
        if len(requests) != 1:
            raise ValueError("each current session requires exactly one request")
        result[session_id] = {
            "request": requests[0],
            "approvals": sorted((r for r in rows if r["kind"] == "APPROVE"), key=lambda r: (r["effective_at"], r["session_event_id"])),
            "revocations": sorted((r for r in rows if r["kind"] == "REVOKE"), key=lambda r: (r["effective_at"], r["session_event_id"])),
        }
    return result


def is_active(session, at, model, memberships):
    request = session["request"]
    if not (timestamp(request["effective_at"]) <= at and timestamp(request["valid_from"]) <= at < timestamp(request["valid_until"])):
        return False
    if any(timestamp(row["effective_at"]) <= at for row in session["revocations"]):
        return False
    role = model["roles"][request["role_id"]]
    approvals = 0
    for row in session["approvals"]:
        if timestamp(row["effective_at"]) <= at:
            paths = membership_paths(memberships, row["approver_id"], at)
            if role["approver_group_id"] in paths:
                approvals += 1
    return approvals >= role["approval_threshold"]


def sod_conflicts(selected_id, sessions, at, model, memberships):
    selected = sessions[selected_id]
    request = selected["request"]
    incompatible = set(model["roles"][request["role_id"]]["incompatible_roles"])
    conflicts = []
    for session_id, session in sessions.items():
        other = session["request"]
        if session_id != selected_id and other["principal_id"] == request["principal_id"] and other["role_id"] in incompatible:
            if timestamp(other["valid_from"]) <= at < timestamp(other["valid_until"]):
                conflicts.append(session_id)
    return sorted(conflicts)

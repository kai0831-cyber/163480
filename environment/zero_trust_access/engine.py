from __future__ import annotations

import hashlib
import json
from typing import Any

from .common import timestamp, validate_payload
from .graph import validate_memberships
from .policy import evaluate
from .sessions import build_sessions, is_active, sod_conflicts
from .visibility import resolve


def _terminal_decision(request: dict[str, Any], reason: str, conflicts: list[str]) -> dict[str, Any]:
    return {
        "request_id": request["request_id"],
        "principal_id": request["principal_id"],
        "resource_id": request["resource_id"],
        "action": request["action"],
        "evaluated_at": request["evaluated_at"],
        "decision": "DENY",
        "reason": reason,
        "governing_policies": [],
        "conflicting_sessions": conflicts,
    }


def evaluate_batch(payload: Any) -> dict[str, Any]:
    model = validate_payload(payload)
    memberships = resolve(
        model["membership_events"], "membership_id", model["cutoff_dt"]
    )
    policies = resolve(model["policy_events"], "policy_id", model["cutoff_dt"])
    session_events = resolve(
        model["session_events"], "session_event_id", model["cutoff_dt"]
    )
    validate_memberships(memberships, model["groups"])
    sessions = build_sessions(session_events)

    decisions: list[dict[str, Any]] = []
    for request in sorted(model["requests"], key=lambda row: row["request_id"]):
        at = timestamp(request["evaluated_at"])
        active_role: str | None = None
        session_id = request["session_id"]
        if session_id is not None:
            session = sessions.get(session_id)
            if (
                session is None
                or session["request"]["principal_id"] != request["principal_id"]
                or not is_active(session, at, model, memberships)
            ):
                decisions.append(_terminal_decision(request, "SESSION_INVALID", []))
                continue
            conflicts = sod_conflicts(session_id, sessions, at, model, memberships)
            if conflicts:
                decisions.append(_terminal_decision(request, "SOD_CONFLICT", conflicts))
                continue
            active_role = session["request"]["role_id"]

        decision, reason, governing = evaluate(
            request, model, policies, memberships, active_role
        )
        decisions.append({
            "request_id": request["request_id"],
            "principal_id": request["principal_id"],
            "resource_id": request["resource_id"],
            "action": request["action"],
            "evaluated_at": request["evaluated_at"],
            "decision": decision,
            "reason": reason,
            "governing_policies": governing,
            "conflicting_sessions": [],
        })

    tenants = sorted({row["tenant_id"] for row in model["principals"].values()})
    totals_by_tenant = {
        tenant: {
            "tenant_id": tenant,
            "requests": 0,
            "allowed": 0,
            "denied": 0,
            "policy_denied": 0,
            "session_denied": 0,
            "sod_denied": 0,
            "no_match": 0,
        }
        for tenant in tenants
    }
    for decision in decisions:
        tenant = model["principals"][decision["principal_id"]]["tenant_id"]
        total = totals_by_tenant[tenant]
        total["requests"] += 1
        if decision["decision"] == "ALLOW":
            total["allowed"] += 1
        else:
            total["denied"] += 1
            counter = {
                "POLICY_DENY": "policy_denied",
                "SESSION_INVALID": "session_denied",
                "SOD_CONFLICT": "sod_denied",
                "NO_MATCH": "no_match",
            }[decision["reason"]]
            total[counter] += 1
    tenant_totals = [totals_by_tenant[tenant] for tenant in tenants]
    digest_payload = {"decisions": decisions, "tenant_totals": tenant_totals}
    encoded = json.dumps(
        digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "as_of": model["as_of"],
        "knowledge_cutoff": model["knowledge_cutoff"],
        "decisions": decisions,
        "tenant_totals": tenant_totals,
        "snapshot_digest": hashlib.sha256(encoded).hexdigest(),
    }

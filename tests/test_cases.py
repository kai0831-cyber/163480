#!/usr/bin/env python3
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import subprocess
import sys

from oracle import expected


RUNNER = Path(__file__).with_name("candidate_runner.py")
CANDIDATE_ROOT = os.environ.get("CANDIDATE_ROOT", "/app")


def base_case():
    return {
        "as_of": "2026-08-25T12:00:00Z",
        "knowledge_cutoff": "2026-08-25T12:00:00Z",
        "principals": [
            {"principal_id": "user", "tenant_id": "acme"},
            {"principal_id": "approver", "tenant_id": "acme"},
            {"principal_id": "idle", "tenant_id": "zeta"},
        ],
        "groups": [{"group_id": "approvers", "tenant_id": "acme"}],
        "roles": [{
            "role_id": "operator", "tenant_id": "acme", "approver_group_id": "approvers",
            "approval_threshold": 1, "max_minutes": 120, "incompatible_roles": [],
        }],
        "resources": [
            {"resource_id": "root", "tenant_id": "acme", "parent_id": None, "labels": {"stage": "prod", "region": "eu"}},
            {"resource_id": "opaque-leaf", "tenant_id": "acme", "parent_id": "root", "labels": {}},
        ],
        "membership_events": [membership("ma", "PRINCIPAL", "approver", "approvers")],
        "policy_events": [policy("allow-role", "ALLOW", "ROLE", "operator", "root", True, {"stage": "prod"})],
        "session_events": [
            session_request("request-op", "s-op", "user", "operator"),
            session_approve("approve-op", "s-op", "approver", "2026-08-25T09:45:00Z"),
        ],
        "requests": [access_request("r-main", "opaque-leaf", "s-op")],
    }


def membership(mid, member_type, member_id, group_id, start="2026-08-25T00:00:00Z", end="2026-08-26T00:00:00Z"):
    return {"membership_id": mid, "revision": 1, "published_at": "2026-08-25T09:00:00Z", "op": "UPSERT", "member_type": member_type, "member_id": member_id, "group_id": group_id, "valid_from": start, "valid_until": end}


def policy(pid, effect, subject_type, subject_id, resource_id, descendants=False, required=None, revision=1, published="2026-08-25T09:00:00Z"):
    return {"policy_id": pid, "revision": revision, "published_at": published, "op": "UPSERT", "effect": effect, "subject_type": subject_type, "subject_id": subject_id, "resource_id": resource_id, "include_descendants": descendants, "actions": ["deploy"], "required_labels": required or {}, "valid_from": "2026-08-25T00:00:00Z", "valid_until": "2026-08-26T00:00:00Z"}


def session_request(event_id, session_id, principal_id, role_id):
    return {"session_event_id": event_id, "revision": 1, "published_at": "2026-08-25T09:30:00Z", "op": "UPSERT", "session_id": session_id, "kind": "REQUEST", "effective_at": "2026-08-25T09:30:00Z", "principal_id": principal_id, "role_id": role_id, "valid_from": "2026-08-25T10:00:00Z", "valid_until": "2026-08-25T11:30:00Z"}


def session_approve(event_id, session_id, approver_id, when):
    return {"session_event_id": event_id, "revision": 1, "published_at": when, "op": "UPSERT", "session_id": session_id, "kind": "APPROVE", "effective_at": when, "approver_id": approver_id}


def access_request(request_id, resource_id, session_id, principal_id="user"):
    return {"request_id": request_id, "principal_id": principal_id, "resource_id": resource_id, "action": "deploy", "evaluated_at": "2026-08-25T10:30:00Z", "session_id": session_id}


def direct_case():
    case = base_case()
    case["policy_events"] = [policy("direct", "ALLOW", "PRINCIPAL", "user", "root")]
    case["requests"] = [access_request("r-direct", "root", None)]
    return case


def run(payload):
    env = os.environ.copy()
    env["CANDIDATE_ROOT"] = CANDIDATE_ROOT
    return subprocess.run(
        [sys.executable, str(RUNNER)], input=json.dumps(payload, ensure_ascii=False),
        text=True, capture_output=True, env=env, timeout=12,
    )


def assert_valid(name, payload):
    want = expected(payload)
    proc = run(payload)
    if proc.returncode != 0:
        raise AssertionError(f"{name}: candidate exited {proc.returncode}: {proc.stderr[:500]}")
    try:
        got = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{name}: invalid JSON: {proc.stdout[:300]}") from exc
    if got != want:
        raise AssertionError(
            f"{name}: integrated result differs\nwant={json.dumps(want, sort_keys=True, ensure_ascii=False)[:1800]}\n"
            f"got ={json.dumps(got, sort_keys=True, ensure_ascii=False)[:1800]}"
        )


def assert_invalid(name, payload):
    proc = run(payload)
    if proc.returncode == 0:
        raise AssertionError(f"{name}: invalid payload was accepted")


def assert_cli(name, payload, valid):
    env = os.environ.copy()
    env["PYTHONPATH"] = CANDIDATE_ROOT
    proc = subprocess.run(
        [sys.executable, "-m", "zero_trust_access.cli"],
        input=json.dumps(payload, ensure_ascii=False), text=True,
        capture_output=True, env=env, cwd=CANDIDATE_ROOT, timeout=12,
    )
    if valid:
        if proc.returncode != 0:
            raise AssertionError(f"{name}: CLI exited {proc.returncode}: {proc.stderr[:500]}")
        want = expected(payload)
        if json.loads(proc.stdout) != want:
            raise AssertionError(f"{name}: CLI output differs from evaluate_batch")
        canonical = json.dumps(want, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        if proc.stdout != canonical:
            raise AssertionError(f"{name}: CLI output is not canonical sorted JSON")
    elif proc.returncode == 0 or not proc.stderr.strip():
        raise AssertionError(f"{name}: CLI accepted invalid input or gave no explanation")


def case_late_lower_revision():
    case = direct_case()
    case["policy_events"] = [
        policy("versioned", "ALLOW", "PRINCIPAL", "user", "root", revision=2, published="2026-08-25T09:00:00Z"),
        policy("versioned", "DENY", "PRINCIPAL", "user", "root", revision=1, published="2026-08-25T11:00:00Z"),
    ]
    return case


def case_retracted():
    case = direct_case()
    case["policy_events"] = [
        policy("gone", "ALLOW", "PRINCIPAL", "user", "root", revision=1),
        {"policy_id": "gone", "revision": 2, "published_at": "2026-08-25T11:00:00Z", "op": "RETRACT"},
    ]
    return case


def case_diamond():
    case = direct_case()
    case["groups"].extend([
        {"group_id": "ga", "tenant_id": "acme"}, {"group_id": "gb", "tenant_id": "acme"},
        {"group_id": "target", "tenant_id": "acme"},
    ])
    case["membership_events"].extend([
        membership("b0", "PRINCIPAL", "user", "ga"), membership("a0", "PRINCIPAL", "user", "gb"),
        membership("a1", "GROUP", "ga", "target"), membership("z1", "GROUP", "gb", "target"),
    ])
    case["policy_events"] = [policy("nested", "ALLOW", "GROUP", "target", "root")]
    return case


def case_approval_time():
    case = base_case()
    case["resources"] = [case["resources"][0]]
    case["requests"] = [access_request("r-time", "root", "s-op")]
    case["policy_events"] = [policy("role-exact", "ALLOW", "ROLE", "operator", "root")]
    case["membership_events"] = [membership("ma", "PRINCIPAL", "approver", "approvers", end="2026-08-25T10:00:00Z")]
    return case


def case_duplicate_approver():
    case = base_case()
    case["roles"][0]["approval_threshold"] = 2
    case["resources"] = [case["resources"][0]]
    case["requests"] = [access_request("r-dup", "root", "s-op")]
    case["policy_events"] = [policy("role-exact", "ALLOW", "ROLE", "operator", "root")]
    case["session_events"].append(session_approve("approve-op-again", "s-op", "approver", "2026-08-25T09:50:00Z"))
    case["session_events"].append(session_approve("approve-self", "s-op", "user", "2026-08-25T09:55:00Z"))
    return case


def case_active_sod():
    case = base_case()
    case["roles"][0]["incompatible_roles"] = ["auditor"]
    case["roles"].append({"role_id": "auditor", "tenant_id": "acme", "approver_group_id": "approvers", "approval_threshold": 1, "max_minutes": 120, "incompatible_roles": ["operator"]})
    case["session_events"].extend([
        session_request("request-audit", "s-audit", "user", "auditor"),
        session_approve("approve-audit", "s-audit", "approver", "2026-08-25T09:45:00Z"),
    ])
    return case


def case_inactive_sod():
    case = case_active_sod()
    case["session_events"] = [row for row in case["session_events"] if row["session_id"] != "s-audit" or row["kind"] == "REQUEST"]
    return case


def case_revoked_session():
    case = base_case()
    case["resources"] = [case["resources"][0]]
    case["policy_events"] = [policy("role-exact", "ALLOW", "ROLE", "operator", "root")]
    case["requests"] = [access_request("r-revoked", "root", "s-op")]
    case["session_events"].append({
        "session_event_id": "revoke-op", "revision": 1,
        "published_at": "2026-08-25T10:15:00Z", "op": "UPSERT",
        "session_id": "s-op", "kind": "REVOKE",
        "effective_at": "2026-08-25T10:15:00Z",
    })
    case["session_events"].append(session_approve("approve-after-revoke", "s-op", "approver", "2026-08-25T10:20:00Z"))
    return case


def case_role_requires_session():
    case = direct_case()
    case["policy_events"] = [policy("role-only", "ALLOW", "ROLE", "operator", "root")]
    case["requests"] = [access_request("r-role-without-session", "root", None)]
    return case


def case_overridden_labels():
    case = direct_case()
    case["resources"] = [
        {"resource_id": "root-node", "tenant_id": "acme", "parent_id": None, "labels": {"region": "eu", "stage": "prod"}},
        {"resource_id": "child-node", "tenant_id": "acme", "parent_id": "root-node", "labels": {"region": "us"}},
    ]
    case["policy_events"] = [policy("label-allow", "ALLOW", "PRINCIPAL", "user", "root-node", True, {"region": "us"})]
    case["requests"] = [access_request("r-label-override", "child-node", None)]
    return case


def case_false_prefix():
    case = direct_case()
    case["resources"] = [
        {"resource_id": "prod", "tenant_id": "acme", "parent_id": None, "labels": {}},
        {"resource_id": "prod-copy", "tenant_id": "acme", "parent_id": None, "labels": {}},
    ]
    case["policy_events"] = [policy("prefix", "ALLOW", "PRINCIPAL", "user", "prod", True)]
    case["requests"] = [access_request("r-prefix", "prod-copy", None)]
    return case


def case_precedence():
    case = direct_case()
    case["groups"].append({"group_id": "users", "tenant_id": "acme"})
    case["membership_events"].append(membership("mu", "PRINCIPAL", "user", "users"))
    case["resources"] = [
        {"resource_id": "r", "tenant_id": "acme", "parent_id": None, "labels": {}},
        {"resource_id": "r-leaf", "tenant_id": "acme", "parent_id": "r", "labels": {}},
    ]
    case["policy_events"] = [
        policy("root-direct", "ALLOW", "PRINCIPAL", "user", "r", True),
        policy("leaf-group", "DENY", "GROUP", "users", "r-leaf"),
    ]
    case["requests"] = [access_request("r-order", "r-leaf", None)]
    return case


def case_deny_tie():
    case = direct_case()
    case["policy_events"] = [
        policy("a-allow", "ALLOW", "PRINCIPAL", "user", "root"),
        policy("b-deny", "DENY", "PRINCIPAL", "user", "root"),
    ]
    return case


def case_multistage_scope_and_precedence():
    case = base_case()
    case["groups"].append({"group_id": "deployers", "tenant_id": "acme"})
    case["membership_events"].append(membership("md", "PRINCIPAL", "user", "deployers"))
    case["resources"] = [
        {"resource_id": "r-9f", "tenant_id": "acme", "parent_id": None, "labels": {"environment": "prod", "region": "eu"}},
        {"resource_id": "node-eu", "tenant_id": "acme", "parent_id": "r-9f", "labels": {"region": "us"}},
        {"resource_id": "svc-prod-2", "tenant_id": "acme", "parent_id": "node-eu", "labels": {"classification": "restricted"}},
        {"resource_id": "object-17", "tenant_id": "acme", "parent_id": "svc-prod-2", "labels": {}},
        {"resource_id": "r-9f-copy", "tenant_id": "acme", "parent_id": None, "labels": {"region": "us", "classification": "restricted"}},
    ]
    case["policy_events"] = [
        policy("ancestor-group", "ALLOW", "GROUP", "deployers", "r-9f", True, {"region": "us", "classification": "restricted"}),
        policy("service-role", "DENY", "ROLE", "operator", "svc-prod-2"),
        policy("leaf-principal", "ALLOW", "PRINCIPAL", "user", "object-17"),
        policy("prefix-sibling", "ALLOW", "PRINCIPAL", "user", "r-9f", True, {"region": "us"}),
    ]
    case["requests"] = [
        access_request("r-deep-session", "object-17", "s-op"),
        access_request("r-sibling", "r-9f-copy", None),
    ]
    return case


def case_nested_approval_and_sod_inputs():
    case = base_case()
    case["groups"].append({"group_id": "delegated", "tenant_id": "acme"})
    case["principals"].append({"principal_id": "approver2", "tenant_id": "acme"})
    case["roles"][0]["approval_threshold"] = 3
    case["membership_events"].extend([
        membership("m2", "PRINCIPAL", "approver2", "delegated", start="2026-08-25T10:00:00Z"),
        membership("m3", "GROUP", "delegated", "approvers"),
    ])
    case["resources"] = [case["resources"][0]]
    case["policy_events"] = [policy("role-check", "ALLOW", "ROLE", "operator", "root")]
    case["requests"] = [access_request("r-nested-approval", "root", "s-op")]
    case["session_events"].extend([
        session_approve("approve-duplicate", "s-op", "approver", "2026-08-25T09:50:00Z"),
        session_approve("approve-self", "s-op", "user", "2026-08-25T09:55:00Z"),
        session_approve("approve-nested", "s-op", "approver2", "2026-08-25T10:15:00Z"),
    ])
    return case


def case_large_graph(size=220):
    case = direct_case()
    case["groups"].extend({"group_id": f"g{i:03d}", "tenant_id": "acme"} for i in range(size))
    case["membership_events"].append(membership("chain-000", "PRINCIPAL", "user", "g000"))
    for i in range(size - 1):
        case["membership_events"].append(membership(f"chain-{i + 1:03d}", "GROUP", f"g{i:03d}", f"g{i + 1:03d}"))
    case["policy_events"] = [policy("deep", "ALLOW", "GROUP", f"g{size - 1:03d}", "root")]
    return case


def permuted(payload, seed):
    result = deepcopy(payload)
    rng = random.Random(seed)
    for key in ("principals", "groups", "roles", "resources", "membership_events", "policy_events", "session_events", "requests"):
        rng.shuffle(result[key])
    return result


def source_policy():
    root = Path(CANDIDATE_ROOT) / "zero_trust_access"
    joined = "\n".join(path.read_text(errors="ignore") for path in root.glob("*.py"))
    for forbidden in ("/tests", "/solution", "sample_case.json", "integrated-inherited-scope", "r-main", "2026-08-25T12:00:00Z"):
        if forbidden in joined:
            raise AssertionError(f"candidate source references verifier material or fixture-specific data: {forbidden}")
    if "13.6" in joined or "121.567" in joined:
        raise AssertionError("candidate source contains fixed answer data")


def invalid_cases():
    cases = []

    def add(name, mutate):
        case = base_case()
        mutate(case)
        cases.append((name, case))

    add("extra-top-level-field", lambda case: case.update(undocumented=1))
    add("post-cutoff-conflict", lambda case: case["policy_events"].append({**case["policy_events"][0], "effect": "DENY", "published_at": "2026-08-26T01:00:00Z"}))

    def membership_revision_conflict(case):
        case["groups"].append({"group_id": "alternate", "tenant_id": "acme"})
        case["membership_events"].append({**case["membership_events"][0], "group_id": "alternate"})
    add("membership-same-revision-conflict", membership_revision_conflict)

    def policy_revision_conflict(case):
        case["policy_events"].append({**case["policy_events"][0], "effect": "DENY"})
    add("policy-same-revision-conflict", policy_revision_conflict)

    def session_revision_conflict(case):
        case["session_events"].append({**case["session_events"][0], "valid_until": "2026-08-25T11:00:00Z"})
    add("session-same-revision-conflict", session_revision_conflict)
    add("resource-cycle", lambda case: case["resources"][0].update(parent_id="opaque-leaf"))

    def member_cycle(case):
        case["groups"].extend([
            {"group_id": "x", "tenant_id": "acme"},
            {"group_id": "y", "tenant_id": "acme"},
        ])
        case["membership_events"].extend([
            membership("xy", "GROUP", "x", "y"),
            membership("yx", "GROUP", "y", "x"),
        ])
    add("membership-cycle", member_cycle)

    add("asymmetric-role", lambda case: case["roles"][0].update(incompatible_roles=["missing"]))
    add("duplicate-request", lambda case: case["requests"].append(deepcopy(case["requests"][0])))
    add("boolean-is-not-integer", lambda case: case["policy_events"][0].update(include_descendants=1))
    add("empty-membership-interval", lambda case: case["membership_events"][0].update(valid_until=case["membership_events"][0]["valid_from"]))
    add("unknown-request-resource", lambda case: case["requests"][0].update(resource_id="unknown-resource"))
    add("boolean-is-not-positive-integer", lambda case: case["roles"][0].update(approval_threshold=True))

    add("invalid-as-of-timestamp", lambda case: case.update(as_of="not-a-timestamp"))
    add("empty-principal-id", lambda case: case["principals"][0].update(principal_id=""))
    add("duplicate-principal-id", lambda case: case["principals"].append(deepcopy(case["principals"][0])))
    add("duplicate-group-id", lambda case: case["groups"].append(deepcopy(case["groups"][0])))
    add("duplicate-role-id", lambda case: case["roles"].append(deepcopy(case["roles"][0])))
    add("empty-resources", lambda case: case.update(resources=[]))
    add("cross-tenant-resource-parent", lambda case: case["resources"].append({"resource_id": "zeta-child", "tenant_id": "zeta", "parent_id": "root", "labels": {}}))
    add("duplicate-resource-id", lambda case: case["resources"].append(deepcopy(case["resources"][0])))
    add("duplicate-actions", lambda case: case["policy_events"][0].update(actions=["deploy", "deploy"]))
    add("empty-actions", lambda case: case["policy_events"][0].update(actions=[]))
    add("invalid-policy-effect", lambda case: case["policy_events"][0].update(effect="MAYBE"))
    add("invalid-policy-subject-type", lambda case: case["policy_events"][0].update(subject_type="TENANT"))
    add("empty-policy-id", lambda case: case["policy_events"][0].update(policy_id=""))
    add("invalid-policy-label-key", lambda case: case["policy_events"][0].update(required_labels={"": "prod"}))
    add("empty-policy-interval", lambda case: case["policy_events"][0].update(valid_until=case["policy_events"][0]["valid_from"]))
    add("duplicate-incompatible-roles", lambda case: case["roles"][0].update(incompatible_roles=["operator", "operator"]))
    add("invalid-label-value", lambda case: case["resources"][0].update(labels={"stage": 1}))

    def cross_tenant_membership(case):
        case["groups"].append({"group_id": "zeta-group", "tenant_id": "zeta"})
        case["membership_events"][0]["group_id"] = "zeta-group"
    add("cross-tenant-membership", cross_tenant_membership)

    def cross_tenant_policy(case):
        case["resources"].append({"resource_id": "zeta-resource", "tenant_id": "zeta", "parent_id": None, "labels": {}})
        case["policy_events"][0]["resource_id"] = "zeta-resource"
    add("cross-tenant-policy", cross_tenant_policy)

    def cross_tenant_session(case):
        case["principals"].append({"principal_id": "zeta-user", "tenant_id": "zeta"})
        case["session_events"][0]["principal_id"] = "zeta-user"
    add("cross-tenant-session-request", cross_tenant_session)

    add("unknown-approver", lambda case: case["session_events"][1].update(approver_id="missing"))
    add("orphan-session-approval", lambda case: case["session_events"].append(session_approve("orphan-approval", "missing-session", "approver", "2026-08-25T09:50:00Z")))
    add("invalid-session-kind", lambda case: case["session_events"][0].update(kind="UNKNOWN"))
    add("request-missing-field", lambda case: case["session_events"][0].pop("role_id"))
    add("approval-extra-field", lambda case: case["session_events"][1].update(extra=1))
    add("published-before-effective", lambda case: case["session_events"][0].update(published_at="2026-08-25T09:00:00Z"))
    add("request-effective-after-start", lambda case: case["session_events"][0].update(effective_at="2026-08-25T10:30:00Z"))
    add("request-empty-interval", lambda case: case["session_events"][0].update(valid_until=case["session_events"][0]["valid_from"]))
    add("request-over-max-duration", lambda case: case["session_events"][0].update(valid_until="2026-08-25T12:30:00Z"))
    add("request-after-as-of", lambda case: case["requests"][0].update(evaluated_at="2026-08-25T13:00:00Z"))

    def multiple_current_requests(case):
        case["session_events"].append(session_request("request-op-2", "s-op", "user", "operator"))
    add("multiple-current-session-requests", multiple_current_requests)
    add("orphan-current-approval", lambda case: case["session_events"].append(session_approve("orphan-current", "missing-session", "approver", "2026-08-25T09:50:00Z")))
    add("orphan-current-revoke", lambda case: case["session_events"].append({
        "session_event_id": "orphan-revoke", "revision": 1,
        "published_at": "2026-08-25T09:50:00Z", "op": "UPSERT",
        "session_id": "missing-session", "kind": "REVOKE",
        "effective_at": "2026-08-25T09:50:00Z",
    }))

    def post_cutoff_bad_membership(case):
        bad = deepcopy(case["membership_events"][0])
        bad["membership_id"] = "post-cutoff-membership"
        bad["published_at"] = "2026-08-26T01:00:00Z"
        bad["group_id"] = "missing-group"
        case["membership_events"].append(bad)
    add("post-cutoff-membership-reference-still-validated", post_cutoff_bad_membership)

    def post_cutoff_bad_policy(case):
        bad = deepcopy(case["policy_events"][0])
        bad["policy_id"] = "post-cutoff-policy"
        bad["published_at"] = "2026-08-26T01:00:00Z"
        bad["subject_id"] = "missing-principal"
        case["policy_events"].append(bad)
    add("post-cutoff-policy-reference-still-validated", post_cutoff_bad_policy)

    def post_cutoff_bad_session(case):
        bad = deepcopy(case["session_events"][0])
        bad["session_event_id"] = "post-cutoff-session"
        bad["published_at"] = "2026-08-26T01:00:00Z"
        bad["role_id"] = "missing-role"
        case["session_events"].append(bad)
    add("post-cutoff-session-reference-still-validated", post_cutoff_bad_session)

    def post_cutoff_bad_schema(case):
        bad = {**case["policy_events"][0], "policy_id": "post-cutoff-schema", "published_at": "2026-08-26T01:00:00Z", "unexpected": 1}
        case["policy_events"].append(bad)
    add("post-cutoff-schema-still-validated", post_cutoff_bad_schema)

    return cases


def duplicate_rows_case():
    case = direct_case()
    for key in ("membership_events", "policy_events", "session_events"):
        case[key].append(deepcopy(case[key][0]))
    return case


def main():
    source_policy()
    cases = [
        ("integrated-inherited-scope", base_case()),
        ("late-lower-revision", case_late_lower_revision()),
        ("authoritative-retraction", case_retracted()),
        ("diamond-shortest-proof", case_diamond()),
        ("approval-time-membership", case_approval_time()),
        ("distinct-nonself-approvals", case_duplicate_approver()),
        ("active-sod-session", case_active_sod()),
        ("inactive-sod-session", case_inactive_sod()),
        ("revoked-session-cannot-reactivate", case_revoked_session()),
        ("role-requires-supplied-session", case_role_requires_session()),
        ("inherited-label-override", case_overridden_labels()),
        ("opaque-resource-identifiers", case_false_prefix()),
        ("resource-before-subject-precedence", case_precedence()),
        ("deny-dominates-tie", case_deny_tie()),
        ("multistage-scope-and-precedence", case_multistage_scope_and_precedence()),
        ("nested-approval-and-sod-inputs", case_nested_approval_and_sod_inputs()),
        ("large-transitive-graph", case_large_graph()),
    ]
    for name, payload in cases:
        assert_valid(name, payload)
    for seed in range(7):
        assert_valid(f"row-permutation-{seed}", permuted(case_diamond(), seed))
    assert_valid("exact-duplicate-ledger-rows", duplicate_rows_case())
    for name, payload in invalid_cases():
        assert_invalid(name, payload)
    assert_cli("cli-valid", direct_case(), True)
    assert_cli("cli-invalid", invalid_cases()[0][1], False)
    print(f"passed {len(cases) + 8} valid, {len(invalid_cases())} invalid, and 2 CLI scenarios")


if __name__ == "__main__":
    main()

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
        if json.loads(proc.stdout) != expected(payload):
            raise AssertionError(f"{name}: CLI output differs from evaluate_batch")
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


def case_inactive_sod():
    case = base_case()
    case["roles"][0]["incompatible_roles"] = ["auditor"]
    case["roles"].append({"role_id": "auditor", "tenant_id": "acme", "approver_group_id": "approvers", "approval_threshold": 1, "max_minutes": 120, "incompatible_roles": ["operator"]})
    case["session_events"].append(session_request("request-audit", "s-audit", "user", "auditor"))
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
    extra = base_case(); extra["undocumented"] = 1
    conflict = base_case(); bad = deepcopy(conflict["policy_events"][0]); bad["effect"] = "DENY"; bad["published_at"] = "2026-08-26T01:00:00Z"; conflict["policy_events"].append(bad)
    cycle = base_case(); cycle["resources"][0]["parent_id"] = "opaque-leaf"
    member_cycle = base_case(); member_cycle["groups"].extend([{"group_id": "x", "tenant_id": "acme"}, {"group_id": "y", "tenant_id": "acme"}]); member_cycle["membership_events"].extend([membership("xy", "GROUP", "x", "y"), membership("yx", "GROUP", "y", "x")])
    asym = base_case(); asym["roles"][0]["incompatible_roles"] = ["missing"]
    duplicate_request = base_case(); duplicate_request["requests"].append(deepcopy(duplicate_request["requests"][0]))
    bad_bool = base_case(); bad_bool["policy_events"][0]["include_descendants"] = 1
    bad_interval = base_case(); bad_interval["membership_events"][0]["valid_until"] = bad_interval["membership_events"][0]["valid_from"]
    bad_reference = base_case(); bad_reference["requests"][0]["resource_id"] = "unknown-resource"
    bad_integer = base_case(); bad_integer["roles"][0]["approval_threshold"] = True
    return [
        ("extra-field", extra), ("post-cutoff-conflict", conflict),
        ("resource-cycle", cycle), ("membership-cycle", member_cycle),
        ("asymmetric-role", asym), ("duplicate-request", duplicate_request),
        ("boolean-is-not-integer", bad_bool), ("empty-membership-interval", bad_interval),
        ("unknown-request-resource", bad_reference), ("boolean-is-not-positive-integer", bad_integer),
    ]


def main():
    source_policy()
    cases = [
        ("integrated-inherited-scope", base_case()),
        ("late-lower-revision", case_late_lower_revision()),
        ("authoritative-retraction", case_retracted()),
        ("diamond-shortest-proof", case_diamond()),
        ("approval-time-membership", case_approval_time()),
        ("distinct-nonself-approvals", case_duplicate_approver()),
        ("inactive-sod-session", case_inactive_sod()),
        ("revoked-session-cannot-reactivate", case_revoked_session()),
        ("role-requires-supplied-session", case_role_requires_session()),
        ("inherited-label-override", case_overridden_labels()),
        ("opaque-resource-identifiers", case_false_prefix()),
        ("resource-before-subject-precedence", case_precedence()),
        ("deny-dominates-tie", case_deny_tie()),
        ("large-transitive-graph", case_large_graph()),
    ]
    for name, payload in cases:
        assert_valid(name, payload)
    for seed in range(7):
        assert_valid(f"row-permutation-{seed}", permuted(case_diamond(), seed))
    for name, payload in invalid_cases():
        assert_invalid(name, payload)
    assert_cli("cli-valid", direct_case(), True)
    assert_cli("cli-invalid", invalid_cases()[0][1], False)
    print(f"passed {len(cases) + 7} valid, {len(invalid_cases())} invalid, and 2 CLI scenarios")


if __name__ == "__main__":
    main()

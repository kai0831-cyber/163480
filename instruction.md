# Restore a bitemporal zero-trust authorization evidence compiler

A security platform compiles point-in-time access decisions for a multi-tenant control plane. The deployed Python package in `/app/zero_trust_access` combines corrected identity memberships, nested groups, approval-gated privileged sessions, separation-of-duty controls, hierarchical resources, and ordered authorization policies. Restore the service while preserving its module layout and public entry point:

```python
zero_trust_access.evaluate_batch(payload)
```

Use only the Python 3.11 standard library. Results must be deterministic, offline, and identical for every permutation of semantically equivalent input rows. Fixture-specific output is prohibited. You may modify files only under `/app/zero_trust_access`.

## Common input rules

The payload is an object containing exactly:

```text
as_of, knowledge_cutoff, principals, groups, roles, resources,
membership_events, policy_events, session_events, requests
```

Every timestamp is a valid whole-second UTC string in `YYYY-MM-DDTHH:MM:SSZ` form. Identifiers, tenant IDs, actions, label keys, and label values are nonempty strings. Lists described as unique may not contain duplicates. Booleans are not integers for this contract. Malformed structures, unknown references, cross-tenant references, conflicting identities, forbidden cycles, and fields not described below are invalid and must raise `ValueError`.

## Masters

`principals`, `groups`, and `roles` contain unique records with exactly:

```text
principal_id, tenant_id
group_id, tenant_id
role_id, tenant_id, approver_group_id, approval_threshold,
max_minutes, incompatible_roles
```

An approval threshold and maximum duration are positive integers. The approver group belongs to the role's tenant. `incompatible_roles` is a unique list of other role IDs in the same tenant, excludes the role itself, and must be symmetric: if A lists B, B lists A.

`resources` is a nonempty list of unique records containing exactly:

```text
resource_id, tenant_id, parent_id, labels
```

`parent_id` is either `null` or another resource in the same tenant. The parent graph is a forest; cycles are invalid. `labels` is an object of string keys and values. Effective labels are applied from root to leaf, with a child value overriding the same inherited key. Resource depth is zero at a root and increases by one per parent edge.

## Bitemporal revision ledgers

Membership, policy, and session-event ledgers share one authority rule. A positive integer `revision` belongs to a logical event ID. Exact duplicate rows are harmless, but different content for the same `(logical ID, revision)` is invalid, including content published after `knowledge_cutoff`.

For each logical ID, consider revisions whose `published_at` is on or before `knowledge_cutoff`. The greatest revision number is authoritative; publication order and physical row order have no authority. If the authoritative row is `RETRACT`, the logical record is absent. If it is `UPSERT`, its full snapshot is current. A lower revision published later never overrides a higher revision. Rows after the cutoff do not affect the snapshot, but their schema and master references are still validated.

A retraction contains exactly its logical ID, `revision`, `published_at`, and `op`. `op` is `UPSERT` or `RETRACT`.

## Membership graph

A membership upsert contains exactly:

```text
membership_id, revision, published_at, op,
member_type, member_id, group_id, valid_from, valid_until
```

`member_type` is `PRINCIPAL` or `GROUP`; `member_id` refers to that type of master. Target and member belong to the same tenant. `valid_from` is strictly before `valid_until`. A group cannot be a member of itself.

After bitemporal selection, all current group-to-group edges must form an acyclic graph even when validity intervals do not overlap. At time `t`, only current edges whose half-open interval contains `t` participate. A principal belongs to every group reachable through active edges.

Evidence for a group subject is a path of membership IDs from the principal outward to that group. Choose the fewest edges; among equally short paths choose the lexicographically smallest sequence of membership IDs. Direct principal and role subjects use an empty path.

## Privileged sessions

A session-event upsert begins with exactly:

```text
session_event_id, revision, published_at, op,
session_id, kind, effective_at
```

The remaining fields depend on `kind`:

- `REQUEST` adds exactly `principal_id`, `role_id`, `valid_from`, and `valid_until`.
- `APPROVE` adds exactly `approver_id`.
- `REVOKE` adds no fields.

Every event is published on or after its effective time. After bitemporal selection, each session has exactly one current request; every current approval or revocation must refer to a session having that request. The request principal and role share a tenant, `effective_at <= valid_from < valid_until`, and the half-open requested interval is no longer than the role's `max_minutes` in exact elapsed time.

At time `t`, a session is active exactly when:

1. its request is effective and `valid_from <= t < valid_until`;
2. no current revocation is effective on or before `t`; and
3. at least `approval_threshold` distinct eligible approvers have current approvals effective on or before `t`.

The requester cannot approve their own session. Repeated approvals by one person count once. Eligibility is evaluated at each approval's own `effective_at`: the approver must belong transitively to the role's approver group at that instant. An ineligible approval contributes nothing. A revocation is irreversible within the current snapshot; later approvals do not reactivate it.

If an access request supplies a session ID, that session must belong to the request principal and be active at the request's evaluation time. Otherwise the decision is immediately `DENY` with reason `SESSION_INVALID`.

For a valid supplied session, inspect every other session for the same principal that is active at the evaluation time. If any has a role incompatible with the supplied session's role, decide `DENY` with reason `SOD_CONFLICT` and report the conflicting active session IDs in lexical order. Inactive sessions never cause this conflict.

## Policies and requests

A policy upsert contains exactly:

```text
policy_id, revision, published_at, op, effect,
subject_type, subject_id, resource_id, include_descendants,
actions, required_labels, valid_from, valid_until
```

`effect` is `ALLOW` or `DENY`. `subject_type` is `PRINCIPAL`, `GROUP`, or `ROLE`; the subject and resource share a tenant. `include_descendants` is boolean. `actions` is a nonempty unique string list. `required_labels` is a string-to-string object. The validity interval is half-open and nonempty.

Each request contains exactly:

```text
request_id, principal_id, resource_id, action,
evaluated_at, session_id
```

Request IDs are unique, `session_id` is a string or `null`, principal and resource share a tenant, and `evaluated_at` is on or before `as_of`.

A current policy is applicable only when:

- the evaluation time is in its validity interval;
- the action is listed;
- its resource is the requested resource, or `include_descendants` is true and the request resource is a descendant through parent edges;
- every required label equals the requested resource's effective label; and
- its subject matches the principal directly, a transitively reachable group, or the role of the valid supplied session.

Resource IDs are opaque; textual prefixes never imply ancestry. A role policy never applies without the corresponding valid supplied session.

Resolve applicable policies by the lexicographic precedence pair:

```text
(policy resource depth, subject rank)
```

where `PRINCIPAL` rank is 3, `ROLE` is 2, and `GROUP` is 1. Keep every policy tied at the greatest pair. If any retained policy is `DENY`, decide `DENY` with `POLICY_DENY`; otherwise decide `ALLOW` with `POLICY_ALLOW`. With no applicable policy, return `DENY` and `NO_MATCH`.

## Output contract

Return exactly `as_of`, `knowledge_cutoff`, `decisions`, `tenant_totals`, and `snapshot_digest`.

`decisions` is ordered by `request_id`. Each row contains exactly:

```text
request_id, principal_id, resource_id, action, evaluated_at,
decision, reason, governing_policies, conflicting_sessions
```

`governing_policies` is empty for `SESSION_INVALID`, `SOD_CONFLICT`, and `NO_MATCH`. Otherwise it is ordered by `policy_id`, with records containing exactly `policy_id`, `effect`, and `subject_path`. Paths follow the evidence rule above. `conflicting_sessions` is nonempty only for `SOD_CONFLICT`.

`tenant_totals` is ordered by `tenant_id`, includes tenants that have principals even with no requests, and contains exactly:

```text
tenant_id, requests, allowed, denied, policy_denied,
session_denied, sod_denied, no_match
```

`policy_denied` counts only `POLICY_DENY`; the other denial counters correspond to `SESSION_INVALID`, `SOD_CONFLICT`, and `NO_MATCH`. All counters are nonnegative integers and `requests = allowed + denied`.

For `snapshot_digest`, serialize exactly `{"decisions": decisions, "tenant_totals": tenant_totals}` using UTF-8 JSON with sorted keys, no insignificant whitespace (`separators=(",", ":")`), and `ensure_ascii=False`, then return its lowercase SHA-256 hexadecimal digest.

## CLI and acceptance

`python -m zero_trust_access.cli` reads one JSON object from standard input and writes one JSON result with sorted keys. Invalid input prints an explanation to standard error and exits nonzero.

The verifier uses unseen tenant, identifier, topology, timestamp, revision, policy, and row-order variants. It covers retractions, late lower revisions, nested and diamond memberships, approval-time membership, duplicate and self approvals, revocation, overlapping incompatible roles, opaque resource IDs, inherited labels, precedence ties, deny dominance, empty tenants, canonical hashes, and invalid structures. It also includes large acyclic graphs and many unrelated policies. Keep the implementation general, auditable, and polynomial in graph and policy size; exhaustive path enumeration is not acceptable.

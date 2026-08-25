from datetime import datetime, timezone
import json
import re


_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def timestamp(value):
    if not isinstance(value, str) or _TS.fullmatch(value) is None:
        raise ValueError("invalid timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("non-canonical timestamp")
    return parsed


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"invalid {label} fields")
    return value


def array(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def ident(value, label="identifier"):
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {label}")
    return value


def positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"invalid {label}")
    return value


def string_list(value, label, nonempty=False):
    result = [ident(item, label) for item in array(value, label)]
    if nonempty and not result:
        raise ValueError(f"empty {label}")
    if len(result) != len(set(result)):
        raise ValueError(f"duplicate {label}")
    return result


def labels(value):
    if not isinstance(value, dict):
        raise ValueError("labels must be an object")
    return {ident(key, "label key"): ident(item, "label value") for key, item in value.items()}


def master(rows, keys, id_key, label):
    result = {}
    for raw in array(rows, label):
        row = exact(raw, keys, label)
        identity = ident(row[id_key], id_key)
        ident(row["tenant_id"], "tenant_id")
        if identity in result:
            raise ValueError(f"duplicate {id_key}")
        result[identity] = dict(row)
    return result


def ledger_conflicts(rows, id_key):
    seen = {}
    for row in rows:
        key = (row[id_key], row["revision"])
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if key in seen and seen[key] != encoded:
            raise ValueError(f"conflicting {id_key} revision")
        seen[key] = encoded


def validate_payload(payload):
    top = {
        "as_of", "knowledge_cutoff", "principals", "groups", "roles", "resources",
        "membership_events", "policy_events", "session_events", "requests",
    }
    data = exact(payload, top, "payload")
    as_of = timestamp(data["as_of"])
    cutoff = timestamp(data["knowledge_cutoff"])
    principals = master(data["principals"], {"principal_id", "tenant_id"}, "principal_id", "principal")
    groups = master(data["groups"], {"group_id", "tenant_id"}, "group_id", "group")

    roles = {}
    role_keys = {
        "role_id", "tenant_id", "approver_group_id", "approval_threshold",
        "max_minutes", "incompatible_roles",
    }
    for raw in array(data["roles"], "roles"):
        row = exact(raw, role_keys, "role")
        role_id = ident(row["role_id"], "role_id")
        tenant = ident(row["tenant_id"], "tenant_id")
        if role_id in roles:
            raise ValueError("duplicate role_id")
        group_id = ident(row["approver_group_id"], "approver_group_id")
        positive_int(row["approval_threshold"], "approval_threshold")
        positive_int(row["max_minutes"], "max_minutes")
        incompatible = string_list(row["incompatible_roles"], "incompatible_roles")
        if role_id in incompatible:
            raise ValueError("self-incompatible role")
        if group_id not in groups or groups[group_id]["tenant_id"] != tenant:
            raise ValueError("invalid approver group")
        roles[role_id] = dict(row)
    for role_id, role in roles.items():
        for other_id in role["incompatible_roles"]:
            other = roles.get(other_id)
            if other is None or other["tenant_id"] != role["tenant_id"] or role_id not in other["incompatible_roles"]:
                raise ValueError("incompatible roles must be symmetric and same-tenant")

    resources = {}
    for raw in array(data["resources"], "resources"):
        row = exact(raw, {"resource_id", "tenant_id", "parent_id", "labels"}, "resource")
        resource_id = ident(row["resource_id"], "resource_id")
        if resource_id in resources:
            raise ValueError("duplicate resource_id")
        ident(row["tenant_id"], "tenant_id")
        if row["parent_id"] is not None:
            ident(row["parent_id"], "parent_id")
        copy = dict(row)
        copy["labels"] = labels(row["labels"])
        resources[resource_id] = copy
    if not resources:
        raise ValueError("resources cannot be empty")
    for resource_id, resource in resources.items():
        parent_id = resource["parent_id"]
        if parent_id is not None and (
            parent_id not in resources or resources[parent_id]["tenant_id"] != resource["tenant_id"]
        ):
            raise ValueError("invalid resource parent")
        seen = set()
        current = resource_id
        while current is not None:
            if current in seen:
                raise ValueError("resource cycle")
            seen.add(current)
            current = resources[current]["parent_id"]

    membership_events = []
    retract = {"membership_id", "revision", "published_at", "op"}
    upsert = retract | {"member_type", "member_id", "group_id", "valid_from", "valid_until"}
    for raw in array(data["membership_events"], "membership_events"):
        if not isinstance(raw, dict):
            raise ValueError("invalid membership event")
        op = raw.get("op")
        row = exact(raw, retract if op == "RETRACT" else upsert, "membership event")
        if op not in {"UPSERT", "RETRACT"}:
            raise ValueError("invalid membership op")
        ident(row["membership_id"], "membership_id")
        positive_int(row["revision"], "revision")
        timestamp(row["published_at"])
        if op == "UPSERT":
            if row["member_type"] not in {"PRINCIPAL", "GROUP"}:
                raise ValueError("invalid member_type")
            member_id = ident(row["member_id"], "member_id")
            group_id = ident(row["group_id"], "group_id")
            member = principals.get(member_id) if row["member_type"] == "PRINCIPAL" else groups.get(member_id)
            target = groups.get(group_id)
            if member is None or target is None or member["tenant_id"] != target["tenant_id"]:
                raise ValueError("invalid membership reference")
            if row["member_type"] == "GROUP" and member_id == group_id:
                raise ValueError("self membership")
            if timestamp(row["valid_from"]) >= timestamp(row["valid_until"]):
                raise ValueError("invalid membership interval")
        membership_events.append(dict(row))
    ledger_conflicts(membership_events, "membership_id")

    policy_events = []
    retract = {"policy_id", "revision", "published_at", "op"}
    upsert = retract | {
        "effect", "subject_type", "subject_id", "resource_id", "include_descendants",
        "actions", "required_labels", "valid_from", "valid_until",
    }
    for raw in array(data["policy_events"], "policy_events"):
        if not isinstance(raw, dict):
            raise ValueError("invalid policy event")
        op = raw.get("op")
        row = exact(raw, retract if op == "RETRACT" else upsert, "policy event")
        if op not in {"UPSERT", "RETRACT"}:
            raise ValueError("invalid policy op")
        ident(row["policy_id"], "policy_id")
        positive_int(row["revision"], "revision")
        timestamp(row["published_at"])
        if op == "UPSERT":
            if row["effect"] not in {"ALLOW", "DENY"} or row["subject_type"] not in {"PRINCIPAL", "GROUP", "ROLE"}:
                raise ValueError("invalid policy kind")
            subject_id = ident(row["subject_id"], "subject_id")
            subject = {"PRINCIPAL": principals, "GROUP": groups, "ROLE": roles}[row["subject_type"]].get(subject_id)
            resource = resources.get(ident(row["resource_id"], "resource_id"))
            if subject is None or resource is None or subject["tenant_id"] != resource["tenant_id"]:
                raise ValueError("invalid policy reference")
            if not isinstance(row["include_descendants"], bool):
                raise ValueError("include_descendants must be boolean")
            string_list(row["actions"], "actions", nonempty=True)
            labels(row["required_labels"])
            if timestamp(row["valid_from"]) >= timestamp(row["valid_until"]):
                raise ValueError("invalid policy interval")
        policy_events.append(dict(row))
    ledger_conflicts(policy_events, "policy_id")

    session_events = []
    retract = {"session_event_id", "revision", "published_at", "op"}
    base = retract | {"session_id", "kind", "effective_at"}
    request_fields = base | {"principal_id", "role_id", "valid_from", "valid_until"}
    approval_fields = base | {"approver_id"}
    for raw in array(data["session_events"], "session_events"):
        if not isinstance(raw, dict):
            raise ValueError("invalid session event")
        op = raw.get("op")
        if op == "RETRACT":
            row = exact(raw, retract, "session event")
        else:
            kind = raw.get("kind")
            fields = request_fields if kind == "REQUEST" else approval_fields if kind == "APPROVE" else base
            row = exact(raw, fields, "session event")
        if op not in {"UPSERT", "RETRACT"}:
            raise ValueError("invalid session op")
        ident(row["session_event_id"], "session_event_id")
        positive_int(row["revision"], "revision")
        published = timestamp(row["published_at"])
        if op == "UPSERT":
            ident(row["session_id"], "session_id")
            if row["kind"] not in {"REQUEST", "APPROVE", "REVOKE"}:
                raise ValueError("invalid session kind")
            effective = timestamp(row["effective_at"])
            if published < effective:
                raise ValueError("session published before effective")
            if row["kind"] == "REQUEST":
                principal = principals.get(ident(row["principal_id"], "principal_id"))
                role = roles.get(ident(row["role_id"], "role_id"))
                if principal is None or role is None or principal["tenant_id"] != role["tenant_id"]:
                    raise ValueError("invalid session request")
                start, end = timestamp(row["valid_from"]), timestamp(row["valid_until"])
                if effective > start or start >= end or (end - start).total_seconds() > role["max_minutes"] * 60:
                    raise ValueError("invalid requested interval")
            elif row["kind"] == "APPROVE" and ident(row["approver_id"], "approver_id") not in principals:
                raise ValueError("unknown approver")
        session_events.append(dict(row))
    ledger_conflicts(session_events, "session_event_id")

    requests = []
    request_ids = set()
    fields = {"request_id", "principal_id", "resource_id", "action", "evaluated_at", "session_id"}
    for raw in array(data["requests"], "requests"):
        row = exact(raw, fields, "request")
        request_id = ident(row["request_id"], "request_id")
        if request_id in request_ids:
            raise ValueError("duplicate request_id")
        request_ids.add(request_id)
        principal = principals.get(ident(row["principal_id"], "principal_id"))
        resource = resources.get(ident(row["resource_id"], "resource_id"))
        if principal is None or resource is None or principal["tenant_id"] != resource["tenant_id"]:
            raise ValueError("invalid request reference")
        ident(row["action"], "action")
        if timestamp(row["evaluated_at"]) > as_of:
            raise ValueError("request after as_of")
        if row["session_id"] is not None:
            ident(row["session_id"], "session_id")
        requests.append(dict(row))

    return {
        "as_of": data["as_of"], "knowledge_cutoff": data["knowledge_cutoff"],
        "as_of_dt": as_of, "cutoff_dt": cutoff, "principals": principals,
        "groups": groups, "roles": roles, "resources": resources,
        "membership_events": membership_events, "policy_events": policy_events,
        "session_events": session_events, "requests": requests,
    }

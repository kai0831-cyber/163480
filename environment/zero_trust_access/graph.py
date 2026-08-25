from collections import defaultdict

from .common import timestamp


def validate_memberships(memberships, groups):
    adjacency = defaultdict(list)
    indegree = {group_id: 0 for group_id in groups}
    seen = set()
    for row in memberships:
        if row["member_type"] == "GROUP":
            edge = (row["member_id"], row["group_id"])
            if edge not in seen:
                seen.add(edge)
                adjacency[edge[0]].append(edge[1])
                indegree[edge[1]] += 1
    ready = sorted(group_id for group_id, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        group_id = ready.pop(0)
        visited += 1
        for target in sorted(adjacency[group_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if visited != len(groups):
        raise ValueError("current membership graph contains a cycle")


def membership_paths(memberships, principal_id, at):
    result = {}
    for row in memberships:
        if timestamp(row["valid_from"]) <= at < timestamp(row["valid_until"]):
            if row["member_type"] == "PRINCIPAL" and row["member_id"] == principal_id:
                path = (row["membership_id"],)
                prior = result.get(row["group_id"])
                if prior is None or path < prior:
                    result[row["group_id"]] = path
    return result


def resource_depth(resources, resource_id):
    depth = 0
    current = resources[resource_id]["parent_id"]
    while current is not None:
        depth += 1
        current = resources[current]["parent_id"]
    return depth


def is_in_scope(resources, policy_resource, requested_resource, include_descendants):
    if policy_resource == requested_resource:
        return True
    return include_descendants and requested_resource.startswith(policy_resource)


def effective_labels(resources, resource_id):
    return dict(resources[resource_id]["labels"])

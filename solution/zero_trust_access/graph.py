from collections import defaultdict
import heapq

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
    starts = []
    adjacency = defaultdict(list)
    for row in memberships:
        if not (timestamp(row["valid_from"]) <= at < timestamp(row["valid_until"])):
            continue
        edge = (row["membership_id"], row["group_id"])
        if row["member_type"] == "PRINCIPAL" and row["member_id"] == principal_id:
            starts.append(edge)
        elif row["member_type"] == "GROUP":
            adjacency[row["member_id"]].append(edge)
    best = {}
    heap = []
    for membership_id, group_id in starts:
        heapq.heappush(heap, (1, (membership_id,), group_id))
    while heap:
        _, path, group_id = heapq.heappop(heap)
        prior = best.get(group_id)
        if prior is not None and (len(prior), prior) <= (len(path), path):
            continue
        best[group_id] = path
        for membership_id, target in sorted(adjacency[group_id]):
            extended = path + (membership_id,)
            prior = best.get(target)
            if prior is None or (len(extended), extended) < (len(prior), prior):
                heapq.heappush(heap, (len(extended), extended, target))
    return best


def resource_depth(resources, resource_id):
    depth = 0
    current = resources[resource_id]["parent_id"]
    while current is not None:
        depth += 1
        current = resources[current]["parent_id"]
    return depth


def is_in_scope(resources, policy_resource, requested_resource, include_descendants):
    current = requested_resource
    while current is not None:
        if current == policy_resource:
            return current == requested_resource or include_descendants
        current = resources[current]["parent_id"]
    return False


def effective_labels(resources, resource_id):
    lineage = []
    current = resource_id
    while current is not None:
        lineage.append(current)
        current = resources[current]["parent_id"]
    result = {}
    for item in reversed(lineage):
        result.update(resources[item]["labels"])
    return result

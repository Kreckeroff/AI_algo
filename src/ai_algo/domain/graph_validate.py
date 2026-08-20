from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


def composition_depth(nodes: List[dict]) -> int:
    """Longest chain of indicator source_node links."""
    by_id = {n["id"]: n for n in nodes if "id" in n}
    memo: Dict[str, int] = {}

    def depth(node_id: str, seen: Set[str]) -> int:
        if node_id in memo:
            return memo[node_id]
        if node_id in seen:
            return 0
        node = by_id.get(node_id)
        if not node or node.get("type") != "indicator":
            memo[node_id] = 0
            return 0
        parent = node.get("source_node")
        if not parent:
            memo[node_id] = 0
            return 0
        seen = set(seen)
        seen.add(node_id)
        d = 1 + depth(parent, seen)
        memo[node_id] = d
        return d

    if not nodes:
        return 0
    return max(depth(n["id"], set()) for n in nodes if "id" in n)


def validate_graph(graph: dict, max_depth: int = 2) -> Optional[str]:
    nodes = graph.get("nodes") or []
    if not nodes:
        return "graph must have nodes"
    d = composition_depth(nodes)
    if d > max_depth:
        return "composition depth {d} exceeds max_depth {m}".format(d=d, m=max_depth)
    return None

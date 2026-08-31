"""
Trace tong-ontology query/reasoning flow.

Builds an OntologyGraph from a synthetic "airport_v2" model + markdown,
then exercises the public query API:
- search_nodes(keyword)        -> ranked keyword hits
- get_node_detail(node_id)     -> node + incident edges
- get_subgraph(node_id, depth) -> Bounded BFS around a node

Falls back to an in-memory stub graph when tong-ontology is not importable.
"""
from __future__ import annotations

import os
import sys

SCENARIO_NAME = "ontology_query_reasoning"

# --------------------------------------------------------------------------- #
# Make tong-ontology importable (same convention as test_tong_ontology_scenario).
# --------------------------------------------------------------------------- #
TONG_ONTOLOGY_ROOT = "/home/dzk/work/codework/tong_agents/tong-ontology"
TONG_ONTOLOGY_PKG = os.path.join(
    TONG_ONTOLOGY_ROOT, "packages", "ontology-builder", "src"
)

if TONG_ONTOLOGY_PKG not in sys.path:
    sys.path.insert(0, TONG_ONTOLOGY_PKG)

USE_REAL = False
try:
    from tong_ontology_builder import (  # type: ignore
        OntologyGraph,
        OntologyNode,
        OntologyEdge,
        OntologyMeta,
    )
    from tong_ontology_builder.types import graph_to_dict  # type: ignore
    USE_REAL = True
    print(f"[scenario:{SCENARIO_NAME}] Imported real tong_ontology_builder OK")
except Exception as e:  # ImportError, ModuleNotFoundError, FileNotFoundError, ...
    print(f"[scenario:{SCENARIO_NAME}] Real import failed: {e}")
    print(f"[scenario:{SCENARIO_NAME}] Falling back to in-memory stub graph")

 # ---- Stub graph (lightweight stand-in for the real types) -------------- #
    class OntologyMeta:  # type: ignore[no-redef]
        def __init__(self, model_dir="", business_dir="",
 file_count=0, built_at=""):
            self.model_dir = model_dir
            self.business_dir = business_dir
            self.file_count = file_count
            self.built_at = built_at

    class OntologyNode:  # type: ignore[no-redef]
        def __init__(self, id, label, type, aliases=None, file=""):
            self.id = id
            self.label = label
            self.type = type
            self.aliases = list(aliases or [])
            self.file = file

    class OntologyEdge:  # type: ignore[no-redef]
        def __init__(self, id, kind, source, predicate, target, file=""):
            self.id = id
            self.kind = kind
            self.source = source
            self.predicate = predicate
            self.target = target
            self.file = file

    class OntologyGraph:  # type: ignore[no-redef]
        def __init__(self, nodes, edges, meta=None):
            self.nodes = list(nodes)
            self.edges = list(edges)
            self.meta = meta or OntologyMeta()

 # Lightweight query API mirroring tong-ontology.
        def search_nodes(self, keyword, top_k=top_k if False else 10):
            kw = keyword.lower()
            scored = []
            for n in self.nodes:
                score = 0
                if kw in n.label.lower():
                    score += 3
                if any(kw in a.lower() for a in n.aliases):
                    score += 2
                if any(kw in nid.lower() for nid in [n.id]):
                    score += 1
                if score > 0:
                    scored.append((score, n))
            scored.sort(key=lambda x: (-x[0], x[1].id))
            return [n for _, n in scored[:top_k]]

        def get_node_detail(self, node_id):
            n = next((x for x in self.nodes if x.id == node_id), None)
            if n is None:
                return None
            incident = [
                e for e in self.edges
                if e.source == node_id or e.target == node_id
            ]
            return {"node": n, "edges": incident}

        def get_subgraph(self, node_id, depth=2):
            visited = set()
            frontier = {node_id}
            for _ in range(depth):
                nxt = set()
                for eid in frontier:
                    nxt.update(
                        e.source for e in self.edges
                        if e.target == eid and e.source not in visited
                    )
                    nxt.update(
                        e.target for e in self.edges
                        if e.source == eid and e.target not in visited
                    )
                visited |= frontier
                frontier = nxt - visited
            visited |= frontier
            sub_nodes = [n for n in self.nodes if n.id in visited]
            sub_edges = [
                e for e in self.edges
                if e.source in visited and e.target in visited
            ]
            return {"nodes": sub_nodes, "edges": sub_edges, "depth": depth}

        # to_dict fallback (real module also exposes graph_to_dict).
        def to_dict(self):
            return {
                "nodes": [
                    {
                        "id": n.id, "label": n.label, "type": n.type,
                        "aliases": n.aliases, "file": n.file,
                    }
                    for n in self.nodes
                ],
                "edges": [
                    {
                        "id": e.id, "kind": e.kind, "source": e.source,
                        "predicate": e.predicate, "target": e.target,
                        "file": e.file,
                    }
                    for e in self.edges
                ],
                "meta": {
                    "model_dir": self.meta.model_dir,
                    "business_dir": self.meta.business_dir,
                    "file_count": self.meta.file_count,
                    "built_at": self.meta.built_at,
                },
            }


# --------------------------------------------------------------------------- #
# Build the "airport_v2" graph: model/ + markdown descriptions.
# --------------------------------------------------------------------------- #
def build_airport_v2_graph():
    """Construct an OntologyGraph modelling the airport_v2 domain."""
    nodes = [
        OntologyNode(
            id="airport_v2.gate",
            label="Gate",
            type="entity",
            aliases=["gate", "boarding_gate", "A1"],
            file="model/airport_v2/gate.md",
        ),
        OntologyNode(
            id="airport_v2.flight",
            label="Flight",
            type="entity",
            aliases=["flight", "departure", "arrival"],
            file="model/airport_v2/flight.md",
        ),
        OntologyNode(
            id="airport_v2.passenger",
            label="Passenger",
            type="entity",
            aliases=["passenger", "traveler", "pax"],
            file="model/airport_v2/passenger.md",
        ),
        OntologyNode(
            id="airport_v2.boarding",
            label="boarding",
            type="operator",
            aliases=["board", "board_flight"],
            file="operators/boarding.md",
        ),
        OntologyNode(
            id="airport_v2.delay",
            label="delay",
            type="operator",
            aliases=["delayed", "postpone"],
            file="operators/delay.md",
        ),
    ]

    edges = [
        OntologyEdge(
            id="e1", kind="triple",
            source="airport_v2.flight",
            predicate="departs_from",
            target="airport_v2.gate",
            file="model/airport_v2/flight.md",
        ),
        OntologyEdge(
            id="e2", kind="triple",
            source="airport_v2.passenger",
            predicate="boards",
            target="airport_v2.boarding",
            file="model/airport_v2/passenger.md",
        ),
        OntologyEdge(
            id="e3", kind="triple",
            source="airport_v2.boarding",
            predicate="uses_gate",
            target="airport_v2.gate",
            file="operators/boarding.md",
        ),
        OntologyEdge(
            id="e4", kind="triple",
            source="airport_v2.delay",
            predicate="delays",
            target="airport_v2.flight",
            file="operators/delay.md",
        ),
    ]

    return OntologyGraph(
        nodes=nodes,
        edges=edges,
        meta=OntologyMeta(
            model_dir="model/airport_v2",
            business_dir="domains/airport",
            file_count=len(nodes) + len(edges),
            built_at="2026-08-31",
        ),
    )


# --------------------------------------------------------------------------- #
# Query helpers that work for both real and stub graphs.
# Real tong_ontology_builder exposes the same surface on OntologyGraph, so
# we just call methods on the graph object directly.
# --------------------------------------------------------------------------- #
def search_nodes(graph, keyword):
    if hasattr(graph, "search_nodes"):
        return graph.search_nodes(keyword)
    # Older builds: emulate by scanning nodes ourselves.
    kw = keyword.lower()
    hits = []
    for n in graph.nodes:
        if kw in n.label.lower() or any(kw in a.lower() for a in n.aliases):
            hits.append(n)
    return hits


def get_node_detail(graph, node_id):
    if hasattr(graph, "get_node_detail"):
        return graph.get_node_detail(node_id)
    n = next((x for x in graph.nodes if x.id == node_id), None)
    if n is None:
        return None
    incident = [
        e for e in graph.edges
        if e.source == node_id or e.target == node_id
    ]
    return {"node": n, "edges": incident}


def get_subgraph(graph, node_id, depth=2):
    if hasattr(graph, "get_subgraph"):
        return graph.get_subgraph(node_id, depth=depth)
    # Fallback BFS
    visited = {node_id}
    frontier = {node_id}
    for _ in range(depth):
        nxt = set()
        for e in graph.edges:
            if e.source in frontier and e.target not in visited:
                nxt.add(e.target)
            if e.target in frontier and e.source not in visited:
                nxt.add(e.source)
        visited |= nxt
        frontier = nxt
    sub_nodes = [n for n in graph.nodes if n.id in visited]
    sub_edges = [
        e for e in graph.edges
        if e.source in visited and e.target in visited
    ]
    return {"nodes": sub_nodes, "edges": sub_edges, "depth": depth}


# --------------------------------------------------------------------------- #
# Main entry.
# --------------------------------------------------------------------------- #
def main() -> dict:
    print(f"[scenario:{SCENARIO_NAME}] start (USE_REAL={USE_REAL})")

    graph = build_airport_v2_graph()
    n_nodes = len(graph.nodes)
    n_edges = len(graph.edges)
    print(f"[scenario:{SCENARIO_NAME}] built airport_v2 graph "
          f"({n_nodes} nodes, {n_edges} edges)")

    # ---- Keyword query ----------------------------------------------------- #
    keyword = "gate"
    hits = search_nodes(graph, keyword)
    print(f"[scenario:{SCENARIO_NAME}] search_nodes('{keyword}') -> "
          f"{len(hits)} hit(s): " + ", ".join(n.id for n in hits))

    # ---- Node detail ------------------------------------------------------- #
    focus_id = "airport_v2.boarding"
    detail = get_node_detail(graph, focus_id)
    if detail is None:
        print(f"[scenario:{SCENARIO_NAME}] get_node_detail('{focus_id}') -> None")
    else:
        node = detail["node"] if isinstance(detail, dict) else detail.node
        inc = detail["edges"] if isinstance(detail, dict) else detail.edges
        print(f"[scenario:{SCENARIO_NAME}] get_node_detail('{focus_id}') -> "
              f"label={node.label} incident_edges={len(inc)}")
        for e in inc:
            print(f"[scenario:{SCENARIO_NAME}]   edge {e.id}: "
                  f"{e.source} -[{e.predicate}]-> {e.target}")

    # ---- Subgraph extraction ---------------------------------------------- #
    sub = get_subgraph(graph, focus_id, depth=2)
    sub_nodes = sub["nodes"] if isinstance(sub, dict) else sub.nodes
    sub_edges = sub["edges"] if isinstance(sub, dict) else sub.edges
    print(f"[scenario:{SCENARIO_NAME}] get_subgraph('{focus_id}', depth=2) -> "
          f"{len(sub_nodes)} nodes, {len(sub_edges)} edges")
    for n in sub_nodes:
        print(f"[scenario:{SCENARIO_NAME}]   node {n.id} ({n.type})")

    # ---- Serialized snapshot for the trace viewer -------------------------- #
    if USE_REAL:
        snapshot = graph_to_dict(graph)
    else:
        snapshot = graph.to_dict() if hasattr(graph, "to_dict") else None    if snapshot is not None:
        print(f"[scenario:{SCENARIO_NAME}] snapshot meta: "
              f"{snapshot['meta']['model_dir']} "
              f"({snapshot['meta']['file_count']} files, "
              f"built {snapshot['meta']['built_at']})")

    print(f"[scenario:{SCENARIO_NAME}] done")
    return {
        "use_real": USE_REAL,
        "nodes": n_nodes,
        "edges": n_edges,
        "hits": [n.id for n in hits],
        "focus": focus_id,
        "subgraph_nodes": len(sub_nodes),
        "subgraph_edges": len(sub_edges),
    }


if __name__ == "__main__":
    main()

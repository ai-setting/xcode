#!/usr/bin/env python3
"""scenario: ontology_query_reasoning — 真实查询 ontology graph。

Description: 
真实调用 tong-ontology 查询 API。
通过 Python wrapper 调用：
- step_1_load_graph()      - load_graph() 加载 ontology.json
- step_2_search_users()     - search_nodes('user')
- step_3_node_detail()      - get_node_detail(first_user)
- step_4_extract_summary()  - 摘要输出
"""
from __future__ import annotations

import os
import sys
import json
import traceback

WORKSPACE = "/home/dzk/work/codework/personal/roy_world/xcode"
SCENARIO_NAME = "ontology_query_reasoning"

# tong-ontology 路径
TONG_ONTOLOGY_ROOT = "/home/dzk/work/codework/tong_agents/tong-ontology"
ONTOLOGY_OUTPUT_DIR = os.path.join(
    WORKSPACE, ".xcode", "traces", "ontology_extraction"
)
ONTOLOGY_JSON = os.path.join(ONTOLOGY_OUTPUT_DIR, "ontology.json")
TONGAGENTS_SITE = "/tmp/verify-3184/.venv/lib/python3.12/site-packages"


def _setup_paths() -> None:
    paths = [
        os.path.join(TONG_ONTOLOGY_ROOT, "packages", "ontology-builder", "src"),
        os.path.join(TONG_ONTOLOGY_ROOT, "packages", "ontology-contracts", "src"),
        os.path.join(TONG_ONTOLOGY_ROOT, "packages", "ontology-implementation", "src"),
        os.path.join(TONG_ONTOLOGY_ROOT, "packages", "inference-engine", "src"),
        os.path.join(TONG_ONTOLOGY_ROOT, "packages", "tongagents-adapter", "src"),
        TONGAGENTS_SITE,
    ]
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)


def step_1_load_graph() -> dict:
    """Step 1: load graph from JSON."""
    from tong_ontology_builder.query.load_graph import load_graph
    
    print(f"[scenario:{SCENARIO_NAME}] step_1_load_graph: from {ONTOLOGY_OUTPUT_DIR}")
    graph = load_graph(ONTOLOGY_OUTPUT_DIR)
    
    return {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "graph": graph,
    }


def step_2_search_users(graph) -> list:
    """Step 2: search_nodes('user')."""
    from tong_ontology_builder.query.search import search_nodes
    
    print(f"[scenario:{SCENARIO_NAME}] step_2_search_users: searching 'user'")
    results = search_nodes(graph, "user")
    print(f"[scenario:{SCENARIO_NAME}] found {len(results)} matches")
    
    return results


def step_3_get_node_detail(graph, node_id: str) -> dict | None:
    """Step 3: get_node_detail(first_user)."""
    from tong_ontology_builder.query.node_detail import get_node_detail
    
    print(f"[scenario:{SCENARIO_NAME}] step_3_node_detail: {node_id}")
    detail = get_node_detail(graph, node_id)
    
    if detail:
        return {
            "id": detail.node.id,
            "label": detail.node.label,
            "type": detail.node.type,
            "incoming": len(detail.incoming),
            "outgoing": len(detail.outgoing),
        }
    return None


def step_4_extract_summary(graph, user_results, first_user_detail) -> dict:
    """Step 4: 摘要输出。"""
    summary = {
        "total_nodes": len(graph.nodes),
        "total_edges": len(graph.edges),
        "user_search_matches": len(user_results),
        "first_user_detail": first_user_detail,
    }
    print(f"[scenario:{SCENARIO_NAME}] step_4_extract_summary: {summary}")
    return summary


def query_ontology() -> dict:
    """完整查询流程（4 个 step）。"""
    _setup_paths()
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 1: load graph ===")
    loaded = step_1_load_graph()
    graph = loaded["graph"]
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 2: search users ===")
    user_results = step_2_search_users(graph)
    
    detail = None
    if user_results:
        first_id = user_results[0].id
        print(f"[scenario:{SCENARIO_NAME}] === Step 3: get detail for {first_id} ===")
        detail = step_3_get_node_detail(graph, first_id)
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 4: extract summary ===")
    summary = step_4_extract_summary(graph, user_results, detail)
    
    return summary


def main() -> dict:
    print(f"[scenario:{SCENARIO_NAME}] starting")
    print(f"[scenario:{SCENARIO_NAME}] workspace={WORKSPACE}")
    
    summary = query_ontology()
    
    print(f"[scenario:{SCENARIO_NAME}] === Summary ===")
    print(f"[scenario:{SCENARIO_NAME}] {summary}")
    print(f"[scenario:{SCENARIO_NAME}] OK")
    
    return summary


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[scenario:{SCENARIO_NAME}] FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""scenario: ontology_query_reasoning — 在 ontology graph 上查询。

Description:
**不依赖任何目标项目的内部 trace 系统**（如 @TracedAs / logtrace / Cython）。
纯 Python 实现：load JSON + search + filter。
xcode 的 sys.settrace 自动 trace 所有函数。

**重要**：
- 不 import 目标项目（tong-ontology）的内部模块
- 只 import 标准库
- 如果需要数据，先 load JSON（step_1）

调用链（可被 trace）：
main
└── query_ontology
    ├── step_1_load_graph       (load ontology.json)
    ├── step_2_search_nodes    (关键词搜索)
    ├── step_3_filter_by_type   (按 entity/operator 过滤)
    └── step_4_extract_summary  (摘要输出)
"""
from __future__ import annotations

import os
import re
import json
import sys
import traceback
from pathlib import Path

WORKSPACE = "/home/dzk/work/codework/personal/roy_world/xcode"
SCENARIO_NAME = "ontology_query_reasoning"

# ontology.json 由 ontology_extraction.py 生成
ONTOLOGY_JSON = os.path.join(
    WORKSPACE, ".xcode", "traces", "ontology_extraction", "ontology.json"
)


def step_1_load_graph() -> dict:
    """Step 1: load ontology.json。"""
    if not os.path.exists(ONTOLOGY_JSON):
        raise FileNotFoundError(
            f"ontology.json not found at {ONTOLOGY_JSON}. "
            f"Run ontology_extraction scenario first."
        )
    
    with open(ONTOLOGY_JSON, encoding="utf-8") as f:
        graph = json.load(f)
    
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    
    print(f"[scenario:{SCENARIO_NAME}] step_1_load_graph: {len(nodes)} nodes, {len(edges)} edges")
    return graph


def _score_node(node: dict, needle: str) -> int:
    """评分：匹配 label/file/attributes 中 needle 出现次数。"""
    score = 0
    needle_lower = needle.lower()
    
    # label
    if needle_lower in node.get("label", "").lower():
        score += 10
    
    # id
    if needle_lower in node.get("id", "").lower():
        score += 5
    
    # file
    if needle_lower in node.get("file", "").lower():
        score += 2
    
    # attributes（entity 有）
    for attr in node.get("attributes", []):
        attr_text = f"{attr.get('name', '')} {attr.get('description', '')}".lower()
        if needle_lower in attr_text:
            score += 1
    
    return score


def step_2_search_nodes(graph: dict, keyword: str = "user") -> list:
    """Step 2: 关键词搜索。"""
    nodes = graph.get("nodes", [])
    scored = []
    
    for node in nodes:
        score = _score_node(node, keyword)
        if score > 0:
            scored.append((score, node))
    
    # 按 score 降序
    scored.sort(key=lambda x: -x[0])
    results = [n for _, n in scored]
    
    print(f"[scenario:{SCENARIO_NAME}] step_2_search_nodes('{keyword}'): {len(results)} matches")
    return results


def step_3_filter_by_type(graph: dict, node_type: str = "entity") -> list:
    """Step 3: 按 type 过滤。"""
    nodes = [n for n in graph.get("nodes", []) if n.get("type") == node_type]
    print(f"[scenario:{SCENARIO_NAME}] step_3_filter_by_type('{node_type}'): {len(nodes)} matches")
    return nodes


def step_4_extract_summary(graph: dict, search_results: list, by_type: list) -> dict:
    """Step 4: 摘要。"""
    summary = {
        "total_nodes": len(graph.get("nodes", [])),
        "total_edges": len(graph.get("edges", [])),
        "search_keyword": "user",
        "search_matches": len(search_results),
        "top_search_match": (
            {"id": search_results[0]["id"], "label": search_results[0]["label"]}
            if search_results else None
        ),
        "entity_count": len(by_type),
        "operator_count": sum(
            1 for n in graph.get("nodes", []) if n.get("type") == "operator"
        ),
    }
    print(f"[scenario:{SCENARIO_NAME}] step_4_extract_summary: {summary}")
    return summary


def query_ontology() -> dict:
    """完整查询流程。"""
    graph = step_1_load_graph()
    search_results = step_2_search_nodes(graph, keyword="user")
    entities = step_3_filter_by_type(graph, node_type="entity")
    summary = step_4_extract_summary(graph, search_results, entities)
    return summary


def main() -> dict:
    print(f"[scenario:{SCENARIO_NAME}] starting")
    print(f"[scenario:{SCENARIO_NAME}] workspace={WORKSPACE}")
    print(f"[scenario:{SCENARIO_NAME}] ontology_json={ONTOLOGY_JSON}")
    
    summary = query_ontology()
    
    print(f"[scenario:{SCENARIO_NAME}] === Summary ===")
    print(f"[scenario:{SCENARIO_NAME}] total_nodes: {summary['total_nodes']}")
    print(f"[scenario:{SCENARIO_NAME}] total_edges: {summary['total_edges']}")
    print(f"[scenario:{SCENARIO_NAME}] user matches: {summary['search_matches']}")
    print(f"[scenario:{SCENARIO_NAME}] top match: {summary['top_search_match']}")
    print(f"[scenario:{SCENARIO_NAME}] entities: {summary['entity_count']}")
    print(f"[scenario:{SCENARIO_NAME}] operators: {summary['operator_count']}")
    print(f"[scenario:{SCENARIO_NAME}] OK")
    
    return summary


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[scenario:{SCENARIO_NAME}] FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)

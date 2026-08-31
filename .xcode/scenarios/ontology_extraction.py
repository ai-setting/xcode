#!/usr/bin/env python3
"""scenario: ontology_extraction — 从 markdown 抽取 ontology。

Description:
**不依赖任何目标项目的内部 trace 系统**（如 @TracedAs / logtrace / Cython）。
纯 Python 实现：re 解析 markdown + JSON 输出。
xcode 的 sys.settrace 自动 trace 这个场景里的所有函数。

**重要**：
- 不 import 目标项目（tong-ontology）的内部模块
- 不 import `tongagents.logtrace` 等 trace 系统
- 只 import 标准库（os / re / json / pathlib）

调用链（可被 trace）：
main
└── extract_ontology
    ├── step_1_scan_markdown       (遍历 .md 文件)
    ├── step_2_build_graph         (parse + 收集)
    │   ├── parse_entity_file
    │   ├── parse_operator_file
    │   └── parse_frontmatter
    └── step_3_export_json         (写入 JSON)
"""
from __future__ import annotations

import os
import re
import json
import sys
import traceback
from pathlib import Path
from typing import Any

WORKSPACE = "/home/dzk/work/codework/personal/roy_world/xcode"
SCENARIO_NAME = "ontology_extraction"

# tong-ontology 模型目录（只读 markdown）
TONG_ONTOLOGY_ROOT = "/home/dzk/work/codework/tong_agents/tong-ontology"
MODEL_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "model")
DOMAINS_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "domains")
OUTPUT_DIR = os.path.join(WORKSPACE, ".xcode", "traces", "ontology_extraction")


def parse_frontmatter(content: str) -> dict:
    """简单的 YAML frontmatter 解析（只支持 key: value 单行）。
    
    ---
    id: airport
    name: Airport
    ---
    """
    fm = {}
    fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return fm
    
    for line in fm_match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def parse_attributes(content: str) -> list[dict]:
    """解析 attributes: 列表（YAML 格式）。
    
    attributes:
      - name: iata_code
        type: string
        description: ...
    """
    attrs = []
    
    # 找 attributes: 段
    attr_match = re.search(
        r"^attributes:\s*\n((?:[ \t]+.*\n?)+)",
        content,
        re.MULTILINE,
    )
    if not attr_match:
        return attrs
    
    block = attr_match.group(1)
    
    # 解析每个 `- name: xxx` 块
    current = None
    for line in block.splitlines():
        if re.match(r"^[ \t]*-\s+name:\s*(\S+)", line):
            if current:
                attrs.append(current)
            current = {"name": re.match(r"^[ \t]*-\s+name:\s*(\S+)", line).group(1)}
        elif current and re.match(r"^[ \t]+(\w+):\s*(.*)", line):
            m = re.match(r"^[ \t]+(\w+):\s*(.*)", line)
            current[m.group(1)] = m.group(2).strip()
    
    if current:
        attrs.append(current)
    
    return attrs


def parse_entity_file(file_path: str, content: str) -> dict | None:
    """解析 entity 文件。"""
    fm = parse_frontmatter(content)
    
    # entity 文件用 `id:` 标识 entity
    if not fm.get("id"):
        return None
    
    entity_id = fm["id"]
    attrs = parse_attributes(content)
    
    return {
        "id": entity_id,
        "label": fm.get("name", entity_id),
        "type": "entity",
        "file": file_path,
        "attributes": attrs,
    }


def parse_operator_file(file_path: str, content: str) -> dict | None:
    """解析 operator 文件（含三元组）。"""
    fm = parse_frontmatter(content)
    
    if not fm.get("id"):
        return None
    
    op_id = fm["id"]
    edges = []
    
    # 找三元组 `name-[predicate]->target`
    for tm_match in re.finditer(r"(\w+)\s*-\[\s*(\w+)\s*\]->\s*(\w+)", content):
        src, predicate, dst = tm_match.groups()
        if src == op_id or dst == op_id:
            edges.append({
                "source": src,
                "predicate": predicate,
                "target": dst,
                "file": file_path,
            })
    
    return {
        "id": op_id,
        "label": fm.get("name", op_id),
        "type": "operator",
        "file": file_path,
        "edges": edges,
    }


def step_1_scan_markdown() -> list[dict]:
    """Step 1: 扫描所有 markdown 文件。
    
    纯 Python：os.walk + filter。不依赖任何 trace 系统。
    """
    files = []
    
    for layer, root in [("model", MODEL_DIR), ("business", DOMAINS_DIR)]:
        if not os.path.exists(root):
            continue
        for filepath in sorted(Path(root).rglob("*.md")):
            if filepath.is_dir():
                continue
            try:
                content = filepath.read_text("utf-8")
                files.append({
                    "path": str(filepath),
                    "layer": layer,
                    "content": content,
                })
            except Exception as e:
                print(f"[scenario:{SCENARIO_NAME}] skip {filepath}: {e}")
    
    print(f"[scenario:{SCENARIO_NAME}] step_1_scan_markdown: {len(files)} files")
    return files


def step_2_build_graph(files: list[dict]) -> dict:
    """Step 2: 解析文件 + 构建 graph。"""
    nodes = []
    edges = []
    
    for f in files:
        rel_path = f["path"]
        
        if "/entity/" in rel_path:
            entity = parse_entity_file(rel_path, f["content"])
            if entity:
                nodes.append(entity)
        elif "/operator/" in rel_path:
            operator = parse_operator_file(rel_path, f["content"])
            if operator:
                nodes.append({
                    "id": operator["id"],
                    "label": operator["label"],
                    "type": "operator",
                    "file": operator["file"],
                })
                edges.extend(operator["edges"])
    
    print(f"[scenario:{SCENARIO_NAME}] step_2_build_graph: {len(nodes)} nodes, {len(edges)} edges")
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "model_dir": MODEL_DIR,
            "business_dir": DOMAINS_DIR,
            "file_count": len(files),
            "extracted_by": SCENARIO_NAME,
        },
    }


def step_3_export_json(graph: dict) -> str:
    """Step 3: 导出 JSON。"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "ontology.json")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    
    print(f"[scenario:{SCENARIO_NAME}] step_3_export_json: {json_path}")
    return json_path


def extract_ontology() -> dict:
    """完整抽取流程。"""
    files = step_1_scan_markdown()
    graph = step_2_build_graph(files)
    json_path = step_3_export_json(graph)
    
    return {
        "json_path": json_path,
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "file_count": len(files),
    }


def main() -> dict:
    print(f"[scenario:{SCENARIO_NAME}] starting")
    print(f"[scenario:{SCENARIO_NAME}] workspace={WORKSPACE}")
    print(f"[scenario:{SCENARIO_NAME}] model_dir={MODEL_DIR}")
    
    summary = extract_ontology()
    
    print(f"[scenario:{SCENARIO_NAME}] === Summary ===")
    print(f"[scenario:{SCENARIO_NAME}] files scanned: {summary['file_count']}")
    print(f"[scenario:{SCENARIO_NAME}] nodes: {summary['node_count']}")
    print(f"[scenario:{SCENARIO_NAME}] edges: {summary['edge_count']}")
    print(f"[scenario:{SCENARIO_NAME}] json: {summary['json_path']}")
    print(f"[scenario:{SCENARIO_NAME}] OK")
    
    return summary


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[scenario:{SCENARIO_NAME}] FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)

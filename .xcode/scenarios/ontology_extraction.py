#!/usr/bin/env python3
"""scenario: ontology_extraction — 真实抽取 ontology graph。

Description: 
真实调用 tong-ontology 抽取 ontology graph。
tong-ontology 内部函数用 Cython 编译（sys.settrace 跨进程追踪不到），
所以我们用 Python wrapper 函数调用 tong-ontology API：
- step_1_scan_model_dir()   - scan model/ 目录
- step_2_scan_domains_dir()  - scan domains/ 目录
- step_3_build_graph()        - 调 tong-ontology 构建 graph
- step_4_verify_outputs()     - 验证输出

每个 step 都是纯 Python 函数，可以 trace 到。
"""
from __future__ import annotations

import os
import sys
import json
import traceback
from pathlib import Path

WORKSPACE = "/home/dzk/work/codework/personal/roy_world/xcode"
SCENARIO_NAME = "ontology_extraction"

# tong-ontology 路径
TONG_ONTOLOGY_ROOT = "/home/dzk/work/codework/tong_agents/tong-ontology"
MODEL_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "model")
DOMAINS_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "domains")
OUTPUT_DIR = os.path.join(WORKSPACE, ".xcode", "traces", "ontology_extraction")

# tongagents site-packages（用于 tong_ontology_builder.tracing）
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


def step_1_scan_model_dir() -> list[dict]:
    """Step 1: scan model/ 目录。"""
    results = []
    root_path = Path(MODEL_DIR)
    if not root_path.exists():
        return results
    
    for filepath in root_path.rglob("*.md"):
        if filepath.is_dir():
            continue
        try:
            content = filepath.read_text("utf-8")
            results.append({
                "absPath": str(filepath),
                "size": len(content),
            })
        except Exception as e:
            print(f"[scenario:{SCENARIO_NAME}] skip {filepath}: {e}")
    
    print(f"[scenario:{SCENARIO_NAME}] step_1_scan_model_dir: {len(results)} files")
    return results


def step_2_scan_domains_dir() -> list[dict]:
    """Step 2: scan domains/ 目录。"""
    results = []
    root_path = Path(DOMAINS_DIR)
    if not root_path.exists():
        return results
    
    for filepath in root_path.rglob("*.md"):
        if filepath.is_dir():
            continue
        try:
            content = filepath.read_text("utf-8")
            results.append({
                "absPath": str(filepath),
                "size": len(content),
            })
        except Exception as e:
            print(f"[scenario:{SCENARIO_NAME}] skip {filepath}: {e}")
    
    print(f"[scenario:{SCENARIO_NAME}] step_2_scan_domains_dir: {len(results)} files")
    return results


def step_3_build_graph() -> dict:
    """Step 3: 调 tong-ontology 构建 graph + 导出制品。"""
    from tong_ontology_builder.graph.write_graph import write_graph_artifacts
    
    print(f"[scenario:{SCENARIO_NAME}] step_3_build_graph: calling tong-ontology write_graph_artifacts()")
    
    result = write_graph_artifacts(
        model_dir=MODEL_DIR,
        output_dir=OUTPUT_DIR,
        business_dir=DOMAINS_DIR,
    )
    
    return {
        "json_path": result.json_path,
        "node_count": len(result.graph.nodes),
        "edge_count": len(result.graph.edges),
    }


def step_4_verify_outputs() -> dict:
    """Step 4: 验证输出文件存在。"""
    files = {}
    
    for name, path in [
        ("json", os.path.join(OUTPUT_DIR, "ontology.json")),
        ("mermaid", os.path.join(OUTPUT_DIR, "ontology.mmd")),
        ("html", os.path.join(OUTPUT_DIR, "ontology.html")),
    ]:
        if os.path.exists(path):
            files[name] = {
                "path": path,
                "size": os.path.getsize(path),
            }
    
    print(f"[scenario:{SCENARIO_NAME}] step_4_verify_outputs: {len(files)} files")
    return files


def extract_ontology() -> dict:
    """完整抽取流程（4 个 step 都可以被 trace）。"""
    _setup_paths()
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 1: scan model directory ===")
    model_files = step_1_scan_model_dir()
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 2: scan domains directory ===")
    business_files = step_2_scan_domains_dir()
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 3: build graph via tong-ontology ===")
    build_result = step_3_build_graph()
    
    print(f"[scenario:{SCENARIO_NAME}] === Step 4: verify outputs ===")
    outputs = step_4_verify_outputs()
    
    return {
        "model_file_count": len(model_files),
        "business_file_count": len(business_files),
        "build": build_result,
        "outputs": outputs,
    }


def main() -> dict:
    print(f"[scenario:{SCENARIO_NAME}] starting")
    print(f"[scenario:{SCENARIO_NAME}] workspace={WORKSPACE}")
    
    summary = extract_ontology()
    
    print(f"[scenario:{SCENARIO_NAME}] === Summary ===")
    print(f"[scenario:{SCENARIO_NAME}] model files: {summary['model_file_count']}")
    print(f"[scenario:{SCENARIO_NAME}] business files: {summary['business_file_count']}")
    print(f"[scenario:{SCENARIO_NAME}] graph nodes: {summary['build']['node_count']}")
    print(f"[scenario:{SCENARIO_NAME}] graph edges: {summary['build']['edge_count']}")
    print(f"[scenario:{SCENARIO_NAME}] json: {summary['build']['json_path']}")
    print(f"[scenario:{SCENARIO_NAME}] OK")
    
    return summary


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[scenario:{SCENARIO_NAME}] FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)

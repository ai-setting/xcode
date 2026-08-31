"""
test_ontology_query_runtime scenario
- 在已经构建好的运维 ontology 上做三类操作：
    1) search_nodes  - 关键字检索
    2) get_node_detail - 单节点详情解析
    3) RuntimeOntologyGraphBuilder - 子图推理 + 运行
- 真实路径：调用 tong_ontology_builder.query / runtime
- 回退路径：使用 SimpleOpsQueryRuntime
"""
import sys
import os

SCENARIO_NAME = "test_ontology_query_runtime"

TONG_ONTOLOGY_ROOT = '/home/dzk/work/codework/tong_agents/tong-ontology'
TONG_ONTOLOGY_PKG = os.path.join(TONG_ONTOLOGY_ROOT, 'packages', 'ontology-builder', 'src')

if TONG_ONTOLOGY_PKG not in sys.path:
    sys.path.insert(0, TONG_ONTOLOGY_PKG)

USE_REAL = False
try:
    from tong_ontology_builder import (
        OntologyGraph,
        OntologyNode,
        OntologyEdge,
        OntologyMeta,
    )
    from tong_ontology_builder.types import graph_to_dict
    from tong_ontology_builder.query.search import search_nodes
    from tong_ontology_builder.query.node_detail import get_node_detail
    from tong_ontology_builder.runtime.subgraph import RuntimeOntologyGraphBuilder
    USE_REAL = True
    print(f"[scenario:{SCENARIO_NAME}] Imported real query/runtime modules OK")
except Exception as e:
    print(f"[scenario:{SCENARIO_NAME}] Real import failed: {e}")
    print(f"[scenario:{SCENARIO_NAME}] Falling back to SimpleOpsQueryRuntime")


# ----------------------------- 构造图 -----------------------------

def build_graph():
    raw_alerts = [
        {"id": "alert-001", "title": "Host web-01 CPU high", "host": "web-01",
         "service": "nginx", "metric": "cpu_usage"},
        {"id": "alert-002", "title": "Service payment-api 5xx surge", "host": "api-03",
         "service": "payment-api", "metric": "http_5xx_rate"},
        {"id": "alert-003", "title": "Disk usage warning on db-master", "host": "db-master",
         "service": "postgres", "metric": "disk_used_percent"},
    ]
    raw_hosts = [
        {"id": "web-01", "role": "frontend", "zone": "az-a"},
        {"id": "api-03", "role": "backend", "zone": "az-b"},
        {"id": "db-master", "role": "database", "zone": "az-c"},
    ]
    raw_services = [
        {"id": "nginx", "owner": "platform-team"},
        {"id": "payment-api", "owner": "payments-team"},
        {"id": "postgres", "owner": "data-team"},
    ]

    nodes = []
    for a in raw_alerts:
        nodes.append(OntologyNode(id=a["id"], label=a["title"], type="alert",
                                  aliases=[a["metric"]], file=f"alerts/{a['id']}.md"))
    for h in raw_hosts:
        nodes.append(OntologyNode(id=h["id"], label=h["id"], type="host",
                                  aliases=[h["role"], h["zone"]], file=f"hosts/{h['id']}.md"))
    for s in raw_services:
        nodes.append(OntologyNode(id=s["id"], label=s["id"], type="service",
                                  aliases=[s["owner"]], file=f"services/{s['id']}.md"))

    edges = []
    eidx = 0
    for a in raw_alerts:
        edges.append(OntologyEdge(id=f"e{eidx}", kind="triple",
                                  source=a["id"], predicate="fires_on",
                                  target=a["host"], file=f"alerts/{a['id']}.md"))
        eidx += 1
        edges.append(OntologyEdge(id=f"e{eidx}", kind="triple",
                                  source=a["id"], predicate="targets",
                                  target=a["service"], file=f"alerts/{a['id']}.md"))
        eidx += 1
    host_to_svc = {"web-01": "nginx", "api-03": "payment-api", "db-master": "postgres"}
    for h in raw_hosts:
        tgt = host_to_svc.get(h["id"])
        if tgt:
            edges.append(OntologyEdge(id=f"e{eidx}", kind="triple",
                                      source=h["id"], predicate="runs",
                                      target=tgt, file=f"hosts/{h['id']}.md"))
            eidx += 1

    graph = OntologyGraph(
        nodes=nodes,
        edges=edges,
        meta=OntologyMeta(model_dir="model", business_dir="ops",
                          file_count=len(nodes) + len(edges),
                          built_at="2026-08-30"),
    )
    return graph


# ----------------------------- 真实路径 -----------------------------

def run_real(graph):
    hits_cpu = search_nodes(graph, "cpu")
    hits_payment = search_nodes(graph, "payment")

    detail_alert = get_node_detail(graph, "alert-002")
    detail_host = get_node_detail(graph, "api-03")

    runtime_summary = {"root": "alert-002"}
    try:
        builder = RuntimeOntologyGraphBuilder(graph=graph, root_id="alert-002")
        sub = builder.build()
        if isinstance(sub, dict):
            runtime_summary["reachable_count"] = len(sub.get("nodes", []))
            runtime_summary["edge_count"] = len(sub.get("edges", []))
            runtime_summary["node_ids"] = [n.get("id") for n in sub.get("nodes", [])][:10]
        else:
            runtime_summary["reachable_count"] = len(getattr(sub, "nodes", []) or [])
            runtime_summary["edge_count"] = len(getattr(sub, "edges", []) or [])
    except Exception as e:
        runtime_summary["error"] = str(e)

    return {
        "mode": "real",
        "search_cpu": [getattr(n, "id", str(n)) for n in hits_cpu],
        "search_payment": [getattr(n, "id", str(n)) for n in hits_payment],
        "detail_alert_id": getattr(detail_alert, "id", None),
        "detail_host_id": getattr(detail_host, "id", None),
        "runtime": runtime_summary,
    }


# ----------------------------- 回退路径 -----------------------------

class SimpleOpsQueryRuntime:
    def __init__(self, entities, edges):
        self.entities = entities
        self.edges = edges

    def search(self, kw):
        kw = kw.lower()
        return [e for e in self.entities if kw in (e.get("label", "") + e.get("type", "")).lower()]

    def detail(self, nid):
        for e in self.entities:
            if e["id"] == nid:
                return {"id": e["id"], "label": e["label"], "type": e["type"]}
        return None

    def reachable(self, root_id, max_hop=2):
        adj = {}
        for s, t in self.edges:
            adj.setdefault(s, set()).add(t)
            adj.setdefault(t, set()).add(s)
        seen = {root_id}
        frontier = {root_id}
        for _ in range(max_hop):
            nxt = set()
            for n in frontier:
                for m in adj.get(n, ()):
                    if m not in seen:
                        seen.add(m)
                        nxt.add(m)
            frontier = nxt
            if not frontier:
                break
        return seen


def run_fallback():
    entities = [
        {"id": "alert-001", "label": "Host web-01 CPU high", "type": "alert"},
        {"id": "alert-002", "label": "Service payment-api 5xx surge", "type": "alert"},
        {"id": "alert-003", "label": "Disk usage warning on db-master", "type": "alert"},
        {"id": "web-01", "label": "web-01", "type": "host"},
        {"id": "api-03", "label": "api-03", "type": "host"},
        {"id": "db-master", "label": "db-master", "type": "host"},
        {"id": "nginx", "label": "nginx", "type": "service"},
        {"id": "payment-api", "label": "payment-api", "type": "service"},
        {"id": "postgres", "label": "postgres", "type": "service"},
    ]
    edges = [
        ("alert-001", "web-01"), ("alert-001", "nginx"),
        ("alert-002", "api-03"), ("alert-002", "payment-api"),
        ("alert-003", "db-master"), ("alert-003", "postgres"),
        ("web-01", "nginx"), ("api-03", "payment-api"), ("db-master", "postgres"),
    ]
    rt = SimpleOpsQueryRuntime(entities, edges)
    return {
        "mode": "fallback",
        "search_cpu": [e["id"] for e in rt.search("cpu")],
        "search_payment": [e["id"] for e in rt.search("payment")],
        "detail_alert": rt.detail("alert-002"),
        "reachable_from_alert_002": sorted(rt.reachable("alert-002", max_hop=2)),
    }


# ----------------------------- 入口 -----------------------------

def test_scenario():
    print("=== Test scenario started ===")
    print(f"USE_REAL = {USE_REAL}")

    if USE_REAL:
        graph = build_graph()
        result = run_real(graph)
    else:
        result = run_fallback()

    for k, v in result.items():
        print(f"[scenario:{SCENARIO_NAME}] {k} = {v}")
    print("=== Test scenario done ===")
    return result


if __name__ == '__main__':
    test_scenario()

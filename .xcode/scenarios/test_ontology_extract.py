"""
test_ontology_extract scenario
- 从自动化运维原始资料（告警、主机、服务、runbook）解析 → 构建 ontology graph
- 优先尝试导入真实 tong-ontology builder；若不可用，使用 SimpleOpsExtractor
"""
import sys
import os
from datetime import datetime

SCENARIO_NAME = "test_ontology_extract"

# 真实 tong-ontology 路径（与其他 scenario 共用）
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
    USE_REAL = True
    print(f"[scenario:{SCENARIO_NAME}] Imported real tong_ontology_builder OK")
except Exception as e:
    print(f"[scenario:{SCENARIO_NAME}] Real import failed: {e}")
    print(f"[scenario:{SCENARIO_NAME}] Falling back to SimpleOpsExtractor")


# ----------------------------- 原始运维资料 -----------------------------

RAW_ALERTS = [
    {
        "id": "alert-001",
        "title": "Host web-01 CPU high",
        "severity": "P2",
        "host": "web-01",
        "service": "nginx",
        "metric": "cpu_usage",
        "value": 92.5,
        "fired_at": "2026-08-30T10:14:00Z",
        "runbook": "runbook-cpu-high.md",
    },
    {
        "id": "alert-002",
        "title": "Service payment-api 5xx surge",
        "severity": "P1",
        "host": "api-03",
        "service": "payment-api",
        "metric": "http_5xx_rate",
        "value": 12.3,
        "fired_at": "2026-08-30T10:21:00Z",
        "runbook": "runbook-5xx-surge.md",
    },
    {
        "id": "alert-003",
        "title": "Disk usage warning on db-master",
        "severity": "P3",
        "host": "db-master",
        "service": "postgres",
        "metric": "disk_used_percent",
        "value": 85.0,
        "fired_at": "2026-08-30T11:02:00Z",
        "runbook": "runbook-disk-cleanup.md",
    },
]

RAW_HOSTS = [
    {"id": "web-01", "role": "frontend", "zone": "az-a", "ip": "10.0.1.11"},
    {"id": "api-03", "role": "backend", "zone": "az-b", "ip": "10.0.2.23"},
    {"id": "db-master", "role": "database", "zone": "az-c", "ip": "10.0.3.7"},
]

RAW_SERVICES = [
    {"id": "nginx", "owner": "platform-team", "tier": "edge"},
    {"id": "payment-api", "owner": "payments-team", "tier": "core"},
    {"id": "postgres", "owner": "data-team", "tier": "core"},
]

RAW_RUNBOOKS = [
    {
        "id": "runbook-cpu-high.md",
        "title": "CPU usage too high",
        "steps": ["ssh host", "top -bn1", "kill top processes"],
        "applies_to": ["cpu_usage"],
    },
    {
        "id": "runbook-5xx-surge.md",
        "title": "5xx surge investigation",
        "steps": ["check upstream", "review recent deploy", "rollback if needed"],
        "applies_to": ["http_5xx_rate"],
    },
    {
        "id": "runbook-disk-cleanup.md",
        "title": "Disk cleanup",
        "steps": ["rotate logs", "archive cold data"],
        "applies_to": ["disk_used_percent"],
    },
]


# ----------------------------- 真实路径 -----------------------------

def build_real_graph() -> dict:
    """用真实 OntologyGraph/Node/Edge 构造图。"""
    nodes = []
    edges = []

    # 节点：alerts / hosts / services / runbooks
    for a in RAW_ALERTS:
        nodes.append(
            OntologyNode(
                id=a["id"],
                label=a["title"],
                type="alert",
                aliases=[a["severity"], a["metric"]],
                file=f"alerts/{a['id']}.md",
            )
        )
    for h in RAW_HOSTS:
        nodes.append(
            OntologyNode(
                id=h["id"],
                label=h["id"],
                type="host",
                aliases=[h["role"], h["zone"]],
                file=f"hosts/{h['id']}.md",
            )
        )
    for s in RAW_SERVICES:
        nodes.append(
            OntologyNode(
                id=s["id"],
                label=s["id"],
                type="service",
                aliases=[s["owner"], s["tier"]],
                file=f"services/{s['id']}.md",
            )
        )
    for r in RAW_RUNBOOKS:
        nodes.append(
            OntologyNode(
                id=r["id"],
                label=r["title"],
                type="runbook",
                aliases=r["steps"],
                file=f"runbooks/{r['id']}",
            )
        )

    # 边：alert --fires_on--> host, alert --targets--> service,
    #     alert --resolved_by--> runbook, host --runs--> service
    edge_idx = 0
    for a in RAW_ALERTS:
        edges.append(
            OntologyEdge(
                id=f"edge_{edge_idx}", kind="triple",
                source=a["id"], predicate="fires_on", target=a["host"],
                file=f"alerts/{a['id']}.md",
            )
        )
        edge_idx += 1
        edges.append(
            OntologyEdge(
                id=f"edge_{edge_idx}", kind="triple",
                source=a["id"], predicate="targets", target=a["service"],
                file=f"alerts/{a['id']}.md",
            )
        )
        edge_idx += 1
        edges.append(
            OntologyEdge(
                id=f"edge_{edge_idx}", kind="triple",
                source=a["id"], predicate="resolved_by", target=a["runbook"],
                file=f"alerts/{a['id']}.md",
            )
        )
        edge_idx += 1

    for h in RAW_HOSTS:
        # 按 zone/role 启发式：frontend->nginx, backend->payment-api, database->postgres
        mapping = {"frontend": "nginx", "backend": "payment-api", "database": "postgres"}
        svc = mapping.get(h["role"])
        if svc:
            edges.append(
                OntologyEdge(
                    id=f"edge_{edge_idx}", kind="triple",
                    source=h["id"], predicate="runs", target=svc,
                    file=f"hosts/{h['id']}.md",
                )
            )
            edge_idx += 1

    graph = OntologyGraph(
        nodes=nodes,
        edges=edges,
        meta=OntologyMeta(
            model_dir="model",
            business_dir="ops",
            file_count=len(nodes),
            built_at=datetime.utcnow().strftime("%Y-%m-%d"),
        ),
    )

    try:
        from tong_ontology_builder.types import graph_to_dict
        return graph_to_dict(graph)
    except Exception:
        # 直接序列化
        return {
            "mode": "real",
            "nodes": [
                {"id": n.id, "label": n.label, "type": n.type}
                for n in graph.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "predicate": e.predicate,
                    "target": e.target,
                }
                for e in graph.edges
            ],
            "meta": {"file_count": graph.meta.file_count, "built_at": graph.meta.built_at},
        }


# ----------------------------- 回退路径 -----------------------------

class SimpleOpsExtractor:
    """在真实 builder 不可用时，把原始运维资料装配成图。"""

    def __init__(self):
        self.nodes = {} # id -> dict
        self.edges = []   # list of dict

    def _add_node(self, nid, label, ntype, aliases=None):
        self.nodes[nid] = {
            "id": nid,
            "label": label,
            "type": ntype,
            "aliases": aliases or [],
        }

    def _add_edge(self, src, pred, tgt):
        self.edges.append({"source": src, "predicate": pred, "target": tgt})

    def ingest_alerts(self, alerts):
        for a in alerts:
            self._add_node(a["id"], a["title"], "alert", [a["severity"], a["metric"]])
            self._add_edge(a["id"], "fires_on", a["host"])
            self._add_edge(a["id"], "targets", a["service"])
            self._add_edge(a["id"], "resolved_by", a["runbook"])

    def ingest_hosts(self, hosts, host_to_service):
        for h in hosts:
            self._add_node(h["id"], h["id"], "host", [h["role"], h["zone"]])
            svc = host_to_service.get(h["role"])
            if svc:
                self._add_edge(h["id"], "runs", svc)

    def ingest_services(self, services):
        for s in services:
            self._add_node(s["id"], s["id"], "service", [s["owner"], s["tier"]])

    def ingest_runbooks(self, runbooks):
        for r in runbooks:
            self._add_node(r["id"], r["title"], "runbook", r["steps"])

    #几个对运维图常见的 query
    def alerts_for_host(self, host_id):
        return [e["source"] for e in self.edges if e["predicate"] == "fires_on" and e["target"] == host_id]

    def runbook_for_alert(self, alert_id):
        for e in self.edges:
            if e["source"] == alert_id and e["predicate"] == "resolved_by":
                return e["target"]
        return None

    def services_run_by_host(self, host_id):
        for e in self.edges:
            if e["source"] == host_id and e["predicate"] == "runs":
                return e["target"]
        return None


def build_fallback_graph() -> dict:
    ex = SimpleOpsExtractor()
    ex.ingest_alerts(RAW_ALERTS)
    ex.ingest_hosts(RAW_HOSTS, host_to_service={
        "frontend": "nginx",
        "backend": "payment-api",
        "database": "postgres",
    })
    ex.ingest_services(RAW_SERVICES)
    ex.ingest_runbooks(RAW_RUNBOOKS)

    # 演示几条典型查询
    api_alerts = ex.alerts_for_host("api-03")
    rb_for_001 = ex.runbook_for_alert("alert-001")
    svc_on_db = ex.services_run_by_host("db-master")

    return {
        "mode": "fallback",
        "nodes": list(ex.nodes.values()),
        "edges": ex.edges,
        "queries": {
            "alerts_for_api-03": api_alerts,
            "runbook_for_alert-001": rb_for_001,
            "service_on_db-master": svc_on_db,
        },
    }


# ----------------------------- 入口 -----------------------------

def main():
    print(f"[scenario:{SCENARIO_NAME}] start mode={'real' if USE_REAL else 'fallback'}")
    try:
        if USE_REAL:
            result = build_real_graph()
        else:
            result = build_fallback_graph()
    except Exception as e:
        print(f"[scenario:{SCENARIO_NAME}] ERROR during extract: {e}")
        raise

    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    print(f"[scenario:{SCENARIO_NAME}] mode={result.get('mode')}")
    print(f"[scenario:{SCENARIO_NAME}] nodes={len(nodes)} edges={len(edges)}")

    # 类型分布
    type_counts = {}
    for n in nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"[scenario:{SCENARIO_NAME}] node_types={type_counts}")

    # 抽一个 alert节点和一条 resolved_by 边演示
    sample_alert = next((n for n in nodes if n.get("type") == "alert"), None)
    if sample_alert:
        print(f"[scenario:{SCENARIO_NAME}] sample_alert={sample_alert['id']} label={sample_alert['label']}")

    if USE_REAL:
        # 真实路径：用 dict 形式打印一条边
        sample_edge = edges[0] if edges else None
        if sample_edge:
            print(
                f"[scenario:{SCENARIO_NAME}] sample_edge={sample_edge['source']} "
                f"-[{sample_edge['predicate']}]-> {sample_edge['target']}"
            )
    else:
        # 回退路径：打印回退 query 结果
        q = result.get("queries", {})
        print(f"[scenario:{SCENARIO_NAME}] queries={q}")

    print(f"[scenario:{SCENARIO_NAME}] end")
    return result


if __name__ == "__main__":
    main()

"""
Tong-Ontology Test Scenario
- Demonstrates: call ontology builder API, build a graph, run reasoning
- Imports real tong-ontology modules from /home/dzk/work/codework/tong_agents/tong-ontology
- Falls back to SimpleOntologyBuilder if real imports fail
"""
import sys
import os

# 真实 tong-ontology 路径
TONG_ONTOLOGY_ROOT = '/home/dzk/work/codework/tong_agents/tong-ontology'
TONG_ONTOLOGY_PKG = os.path.join(TONG_ONTOLOGY_ROOT, 'packages', 'ontology-builder', 'src')

if TONG_ONTOLOGY_PKG not in sys.path:
    sys.path.insert(0, TONG_ONTOLOGY_PKG)

USE_REAL = False
try:
    from tong_ontology_builder import OntologyGraph, OntologyNode, OntologyEdge, OntologyMeta
    USE_REAL = True
    print("[scenario] Imported real tong_ontology_builder OK")
except Exception as e:
    print(f"[scenario] Real import failed: {e}")
    print("[scenario] Will fallback to SimpleOntologyBuilder")


def build_real_graph() -> dict:
    """真实路径：用 tong_ontology_builder 构造 OntologyGraph"""
    # 构造节点
    n_alice = OntologyNode(
        id='user_alice',
        label='Alice',
        type='entity',
        aliases=['alice', 'A'],
        file='domains/users/alice.md',
    )
    n_bob = OntologyNode(
        id='user_bob',
        label='Bob',
        type='entity',
        aliases=['bob', 'B'],
        file='domains/users/bob.md',
    )
    n_greet = OntologyNode(
        id='op_greet',
        label='greet',
        type='operator',
        aliases=['hello', 'say_hi'],
        file='operators/greet.md',
    )

    # 构造边
    e1 = OntologyEdge(
        id='edge_1', kind='triple',
        source='user_alice', predicate='responds_to', target='op_greet',
        file='domains/users/alice.md',
    )
    e2 = OntologyEdge(
        id='edge_2', kind='triple',
        source='user_bob', predicate='responds_to', target='op_greet',
        file='domains/users/bob.md',
    )

    graph = OntologyGraph(
        nodes=[n_alice, n_bob, n_greet],
        edges=[e1, e2],
        meta=OntologyMeta(
            model_dir='model',
            business_dir='domains',
            file_count=3,
            built_at='2026-08-26',
        ),
    )

    # 调用 builtin：graph_to_dict
    from tong_ontology_builder.types import graph_to_dict
    return graph_to_dict(graph)


class SimpleOntologyBuilder:
    """Fallback: 在没有 tong-ontology 时也能跑通"""

    def __init__(self):
        self.entities = {}
        self.operators = {}

    def add_entity(self, id, name, age):
        self.entities[id] = {'id': id, 'name': name, 'age': age}
        return self

    def add_operator(self, id, logic):
        self.operators[id] = logic
        return self

    def execute(self, op_id, params):
        op = self.operators.get(op_id)
        if op is None:
            raise ValueError(f"Operator not found: {op_id}")
        return op(**params)

    def query(self, sql):
        return list(self.entities.values())


def build_fallback_graph() -> dict:
    """回退路径：使用 SimpleOntologyBuilder"""
    builder = SimpleOntologyBuilder()
    builder.add_entity(id='user_1', name='Alice', age=30)
    builder.add_entity(id='user_2', name='Bob', age=25)
    builder.add_operator(id='greet', logic=lambda name: f"Hello, {name}!")
    builder.add_operator(id='is_adult', logic=lambda age: age >= 18)

    greeting = builder.execute('greet', {'name': 'Alice'})
    is_adult = builder.execute('is_adult', {'age': 30})

    return {
        'mode': 'fallback',
        'entities': list(builder.entities.values()),
        'greeting': greeting,
        'is_adult': is_adult,
    }


def test_scenario():
    """用户视角的 scenario：构建 ontology + 查询"""
    print("=== Test scenario started ===")
    print(f"USE_REAL = {USE_REAL}")

    if USE_REAL:
        result = build_real_graph()
        print(f"[scenario] Real graph nodes: {len(result['nodes'])}, edges: {len(result['edges'])}")
        print(f"[scenario] Sample node: {result['nodes'][0]['label']}")
        print(f"[scenario] Sample edge: {result['edges'][0]['source']} -[{result['edges'][0]['predicate']}]-> {result['edges'][0]['target']}")
    else:
        result = build_fallback_graph()
        print(f"[scenario] Fallback entities: {len(result['entities'])}")
        print(f"[scenario] Greeting: {result['greeting']}")
        print(f"[scenario] Is adult: {result['is_adult']}")

    print("=== Test scenario done ===")
    return result


if __name__ == '__main__':
    test_scenario()
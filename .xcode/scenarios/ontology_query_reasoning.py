#!/usr/bin/env python3
"""scenario: ontology_query_reasoning — call markdown-ontology-business sub-agent.

Description: 真实调用 roy-agent sub-agent 基于 ontology 做业务推理。

工作流：
1. subprocess 调 `roy-agent act -a markdown-ontology-business <prompt>`
2. prompt 包含已有 ontology 路径 + 业务查询/推理任务
3. business agent 会基于 model 生成 grounded instance markdown，
   执行查询（incident edges / subgraph / verifier）
4. 输出 trace tree 显示业务推理调用链

之前是 mock：内嵌 stub graph + 在内存中模拟 search_nodes/get_subgraph。
现在真正驱动 sub-agent 干活，让 trace tree 反映真实推理路径。
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback

WORKSPACE = "/home/dzk/work/codework/personal/roy_world/xcode"
SCENARIO_NAME = "ontology_query_reasoning"

# tong-ontology 路径（已抽取的 model + business 目录）
TONG_ONTOLOGY_ROOT = "/home/dzk/work/codework/tong_agents/tong-ontology"
MODEL_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "model")
DOMAINS_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "domains", "airport")

# sub-agent 配置
BUSINESS_AGENT = "markdown-ontology-business"

# 调用超时（10 分钟）
SUBPROCESS_TIMEOUT = 600


def build_business_prompt() -> str:
    """构造给 markdown-ontology-business 的 prompt。

    包含：
    - 输入：已有 model 路径
    - 业务场景：3 个推理任务
    - 输出要求
    """
    prompt = (
        f"基于已有 Typed Markdown Ontology model，做以下业务推理：\n\n"
        f"**输入 ontology**：\n"
        f"- model 目录：{MODEL_DIR}\n"
        f"- domains 实现：{DOMAINS_DIR}\n\n"
        f"**任务 1 — 查询 incident edges**：\n"
        f"- 找到所有 Entity（user_xxx）的 incident edges\n"
        f"- 列出每个 user 节点的 incident 边（入边+出边）\n\n"
        f"**任务 2 — subgraph 提取**：\n"
        f"- 给定 user_alice，返回 subgraph（depth=2）\n"
        f"- 包含 nodes + edges + metadata\n\n"
        f"**任务 3 — Verifier 验证**：\n"
        f"- 验证所有 rule 约束（TM001-TM011, TM020, TM021）\n"
        f"- 输出每条规则的检查结果（PASS/FAIL）\n"
        f"- 如有 FAIL，给出修复建议\n\n"
        f"**输出要求**：\n"
        f"1. 任务 1 输出格式：`user_id | incident_count | edges_list`\n"
        f"2. 任务 2 输出格式：JSON `{{nodes: [...], edges: [...], depth: 2}}`\n"
        f"3. 任务 3 输出格式：表格 `rule_code | status | message`\n"
        f"4. 最后给出整体摘要：ontology 健康度 + 业务可用性评估\n\n"
        f"**约束**：\n"
        f"- 不得修改 model/ 下的 schema 定义\n"
        f"- 业务实例写到 `domains/airport/` 下（如有新增）\n"
        f"- 完成后用 `ontology validate --model {MODEL_DIR} --business {DOMAINS_DIR}` 验证\n"
    )
    return prompt


def run_business(prompt: str) -> tuple[int, str, str]:
    """subprocess 调用 markdown-ontology-business sub-agent。

    Returns:
        (returncode, stdout, stderr)
    """
    print(f"[scenario:{SCENARIO_NAME}] invoking sub-agent: {BUSINESS_AGENT}")
    print(f"[scenario:{SCENARIO_NAME}] model_dir={MODEL_DIR}")
    print(f"[scenario:{SCENARIO_NAME}] business_dir={DOMAINS_DIR}")

    result = subprocess.run(
        ["roy-agent", "act", "-a", BUSINESS_AGENT, prompt],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        cwd=TONG_ONTOLOGY_ROOT,
    )

    return result.returncode, result.stdout, result.stderr


def main() -> dict:
    print(f"[scenario:{SCENARIO_NAME}] starting")
    print(f"[scenario:{SCENARIO_NAME}] workspace={WORKSPACE}")
    print(f"[scenario:{SCENARIO_NAME}] model_dir={MODEL_DIR}")
    print(f"[scenario:{SCENARIO_NAME}] business_dir={DOMAINS_DIR}")
    print(f"[scenario:{SCENARIO_NAME}] agent={BUSINESS_AGENT}")

    # 1. 构造 prompt
    prompt = build_business_prompt()
    print(f"[scenario:{SCENARIO_NAME}] prompt_length={len(prompt)} chars")

    # 2. subprocess 调用 sub-agent
    returncode, stdout, stderr = run_business(prompt)

    # 3. 处理结果
    if returncode != 0:
        print(f"[scenario:{SCENARIO_NAME}] FAILED (returncode={returncode})")
        print(f"[scenario:{SCENARIO_NAME}] stderr (last 1000 chars):")
        print(stderr[-1000:])
        sys.exit(1)

    # 4. 输出摘要
    print(f"[scenario:{SCENARIO_NAME}] business agent returned successfully")
    print(f"[scenario:{SCENARIO_NAME}] stdout_length={len(stdout)} chars")
    if stdout:
        print(f"[scenario:{SCENARIO_NAME}] --- Output (first 800 chars) ---")
        print(stdout[:800])
        if len(stdout) > 800:
            print(f"[scenario:{SCENARIO_NAME}] ... ({len(stdout) - 800} more chars)")

    print(f"[scenario:{SCENARIO_NAME}] OK")

    return {
        "scenario": SCENARIO_NAME,
        "agent": BUSINESS_AGENT,
        "model_dir": MODEL_DIR,
        "business_dir": DOMAINS_DIR,
        "returncode": returncode,
        "stdout_length": len(stdout),
    }


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired:
        print(f"[scenario:{SCENARIO_NAME}] TIMEOUT after {SUBPROCESS_TIMEOUT}s")
        sys.exit(2)
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""scenario: ontology_extraction — call markdown-ontology-extractor sub-agent.

Description: 真实调用 roy-agent sub-agent 从业务文档抽取 ontology。

工作流：
1. subprocess 调 `roy-agent act -a markdown-ontology-extractor <prompt>`
2. prompt 包含 tong-ontology model 目录路径 + 抽取要求
3. extractor 会读取文档、识别 Entity/Operator、生成符合 SPG/TPG 规范的 markdown
4. 输出 trace tree 显示整个调用链（agent act → sub-agent → 工具调用）

之前是 mock：只 print 一行 OK。现在真正驱动 sub-agent 干活。
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback

WORKSPACE = "/home/dzk/work/codework/personal/roy_world/xcode"
SCENARIO_NAME = "ontology_extraction"

# tong-ontology 模型目录（已存在 SPG/TPG 模型）
TONG_ONTOLOGY_ROOT = "/home/dzk/work/codework/tong_agents/tong-ontology"
MODEL_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "model")
DOMAINS_DIR = os.path.join(TONG_ONTOLOGY_ROOT, "domains")

# sub-agent 配置路径
EXTRACTOR_AGENT = "markdown-ontology-extractor"

# 调用超时（10 分钟）
SUBPROCESS_TIMEOUT = 600


def build_extractor_prompt() -> str:
    """构造给 markdown-ontology-extractor 的 prompt。

    包含：
    - 输入文档路径
    - 输出位置
    - 抽取规范要点
    """
    prompt = (
        f"请使用 Typed Markdown Ontology 规范从以下位置抽取 ontology：\n\n"
        f"**输入文档**：\n"
        f"- model 目录：{MODEL_DIR}\n"
        f"- domains 目录：{DOMAINS_DIR}\n\n"
        f"**任务**：\n"
        f"1. 读取 model/entity/ 和 model/operator/ 下的现有定义\n"
        f"2. 读取 domains/airport/ 下的业务实现文档\n"
        f"3. 识别缺失的 Entity（SPG）和 Operator（TPG）\n"
        f"4. 在 {MODEL_DIR}/ 下补充新 entity/operator 文件（含 ## 属性 表格）\n"
        f"5. 更新 {MODEL_DIR}/aviation-model.md（添加三元组连接 entity 和 operator）\n"
        f"6. 确保所有 link definition title 是 `entity` 或 `operator`（不能用 relation）\n"
        f"7. Attribute type 必须是合法值（string/integer/number/boolean/date/enum/ref:xxx）\n"
        f"8. 完成后输出抽取摘要：新增 entity 数 + 新增 operator 数 + 修复 TM 错误数\n\n"
        f"**约束**：\n"
        f"- 不得修改已存在的 entity 定义\n"
        f"- 不得创建 `model/relation/` 目录\n"
        f"- 三元组只在 TPG 侧使用（TM011）\n"
        f"- 完成后用 `ontology validate --model {MODEL_DIR}` 验证 0 TM errors\n"
    )
    return prompt


def run_extractor(prompt: str) -> tuple[int, str, str]:
    """subprocess 调用 markdown-ontology-extractor sub-agent。

    Returns:
        (returncode, stdout, stderr)
    """
    print(f"[scenario:{SCENARIO_NAME}] invoking sub-agent: {EXTRACTOR_AGENT}")
    print(f"[scenario:{SCENARIO_NAME}] model_dir={MODEL_DIR}")

    result = subprocess.run(
        ["roy-agent", "act", "-a", EXTRACTOR_AGENT, prompt],
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
    print(f"[scenario:{SCENARIO_NAME}] agent={EXTRACTOR_AGENT}")

    # 1. 构造 prompt
    prompt = build_extractor_prompt()
    print(f"[scenario:{SCENARIO_NAME}] prompt_length={len(prompt)} chars")

    # 2. subprocess 调用 sub-agent
    returncode, stdout, stderr = run_extractor(prompt)

    # 3. 处理结果
    if returncode != 0:
        print(f"[scenario:{SCENARIO_NAME}] FAILED (returncode={returncode})")
        print(f"[scenario:{SCENARIO_NAME}] stderr (last 1000 chars):")
        print(stderr[-1000:])
        sys.exit(1)

    # 4. 输出摘要
    print(f"[scenario:{SCENARIO_NAME}] extractor returned successfully")
    print(f"[scenario:{SCENARIO_NAME}] stdout_length={len(stdout)} chars")
    if stdout:
        print(f"[scenario:{SCENARIO_NAME}] --- Output (first 800 chars) ---")
        print(stdout[:800])
        if len(stdout) > 800:
            print(f"[scenario:{SCENARIO_NAME}] ... ({len(stdout) - 800} more chars)")

    print(f"[scenario:{SCENARIO_NAME}] OK")

    return {
        "scenario": SCENARIO_NAME,
        "agent": EXTRACTOR_AGENT,
        "model_dir": MODEL_DIR,
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

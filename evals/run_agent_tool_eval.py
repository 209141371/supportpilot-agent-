import asyncio
import json
import sys
from pathlib import Path

from agents import Runner
from agents.items import ToolCallItem


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(
    0,
    str(SRC_DIR),
)

sys.path.insert(
    0,
    str(ROOT_DIR / "evals"),
)


from eval_logging import log_eval_failure
from supportpilot.agent import create_support_agent
from supportpilot.db import init_db


CASES_PATH = ROOT_DIR / "evals" / "agent_tool_cases.jsonl"

MIN_TOOL_ACCURACY = 1.0


def load_cases() -> list[dict]:
    """加载 Agent Tool Eval 测试用例。"""

    cases = []

    with CASES_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            cases.append(
                json.loads(line)
            )

    return cases


def extract_tool_names(result) -> list[str]:
    """从 Runner 结果中提取本轮调用过的 Tool 名称。"""

    tool_names = []

    for item in result.new_items:
        if not isinstance(
            item,
            ToolCallItem,
        ):
            continue

        raw_item = item.raw_item

        tool_name = getattr(
            raw_item,
            "name",
            None,
        )

        if tool_name:
            tool_names.append(
                tool_name
            )

    return tool_names


async def evaluate_case(
    agent,
    case: dict,
) -> bool:
    """评估单条 Agent Tool Calling 用例。"""

    query = case["query"]
    expected_tool = case["expected_tool"]

    result = await Runner.run(
        agent,
        query,
    )

    tool_names = extract_tool_names(
        result
    )

    passed = (
        expected_tool
        in tool_names
    )

    if not passed:
        log_eval_failure(
            suite="agent_tool",
            case=query,
            expected={
                "tool": expected_tool,
            },
            actual={
                "tools": tool_names,
            },
        )

    print()
    print("-" * 50)
    print(f"Query: {query}")
    print(f"Expected tool: {expected_tool}")
    print(f"Actual tools: {tool_names}")
    print(
        f"Result: {'PASS' if passed else 'FAIL'}"
    )

    return passed


async def main() -> None:
    init_db()

    agent = create_support_agent()

    cases = load_cases()

    passed_count = 0

    for case in cases:
        passed = await evaluate_case(
            agent,
            case,
        )

        if passed:
            passed_count += 1

    total_count = len(cases)

    accuracy = (
        passed_count / total_count
        if total_count
        else 0
    )

    print()
    print("=" * 50)
    print("Agent Tool Calling Eval Summary")
    print("=" * 50)

    print(
        f"Passed: "
        f"{passed_count}/{total_count}"
    )

    print(
        f"Accuracy: "
        f"{accuracy:.2%}"
    )

    print()
    print("=" * 50)
    print("Agent Tool Quality Gate")
    print("=" * 50)

    if accuracy >= MIN_TOOL_ACCURACY:
        print("Status: PASS")
    else:
        print("Status: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(
        main()
    )
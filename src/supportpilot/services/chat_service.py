from dataclasses import dataclass
from typing import Any

from agents import Runner
from agents.items import ToolCallOutputItem

from supportpilot.agent import create_support_agent


MAX_HISTORY_MESSAGES = 10
APPROVAL_REQUIRED_MARKER = "[APPROVAL_REQUIRED]"


@dataclass
class ChatResult:
    """一次客服对话的结构化结果。"""

    answer: str
    conversation: list[dict[str, str]]
    approval_request: dict[str, str] | None = None


def parse_approval_request(text: str) -> dict[str, str] | None:
    """解析写操作工具返回的审批请求。"""

    if APPROVAL_REQUIRED_MARKER not in text:
        return None

    result: dict[str, str] = {}

    for line in text.splitlines():
        line = line.strip()

        if not line or line == APPROVAL_REQUIRED_MARKER or "=" not in line:
            continue

        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()

    if "action" not in result:
        return None

    return result


def find_approval_request(run_result: Any) -> dict[str, str] | None:
    """从 Agent 的原始工具输出中寻找审批请求。"""

    for item in run_result.new_items:
        if not isinstance(item, ToolCallOutputItem):
            continue

        output = item.output

        if not isinstance(output, str):
            continue

        request = parse_approval_request(output)

        if request is not None:
            return request

    return None


async def process_chat_message(
    message: str,
    conversation: list[dict[str, str]] | None = None,
) -> ChatResult:
    """处理一条消息，供 CLI 和 FastAPI 共同调用。"""

    history = list(conversation or [])
    history.append({"role": "user", "content": message})
    history = history[-MAX_HISTORY_MESSAGES:]

    # Agent 负责理解请求和选择工具，业务写入仍由后续审批流程控制。
    agent = create_support_agent()
    result = await Runner.run(agent, history)
    approval_request = find_approval_request(result)

    if approval_request is not None:
        answer = "该操作需要人工审批，请在审批面板中决定是否执行。"
    else:
        answer = result.final_output

    history.append({"role": "assistant", "content": answer})
    history = history[-MAX_HISTORY_MESSAGES:]

    return ChatResult(
        answer=answer,
        conversation=history,
        approval_request=approval_request,
    )

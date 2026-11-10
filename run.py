import json
from datetime import datetime
import asyncio
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(
    0,
    str(SRC_DIR),
)


from supportpilot.db import (
    create_ticket_in_db,
    init_db,
    update_ticket_status_in_db,
)
from supportpilot.workflows.shipping_workflow import (
    approve_shipping_ticket,
    reject_shipping_ticket,
    run_shipping_workflow,
)
from supportpilot.services.chat_service import process_chat_message


APPROVAL_LOG_PATH = Path(
    "data/logs/approval_log.jsonl"
)


def extract_order_id(text: str) -> str | None:
    """从用户输入中提取订单号，例如 A1004。"""

    match = re.search(
        r"A\d+",
        text.upper(),
    )

    if match is None:
        return None

    return match.group()


def should_run_shipping_workflow(text: str) -> bool:
    """判断用户是否想处理物流异常。"""

    shipping_keywords = [
        "物流异常",
        "物流超时",
        "没发货",
        "未发货",
        "发货太慢",
        "发货异常",
        "一直没发货",
        "处理物流",
    ]

    return any(
        keyword in text
        for keyword in shipping_keywords
    )


def handle_shipping_workflow(order_id: str) -> None:
    """运行物流异常 Workflow，并处理人工审批。"""

    state = run_shipping_workflow(
        order_id,
    )

    # 不需要审批时，直接展示 Workflow 结果
    if state.current_step != "awaiting_approval":
        print()
        print("=" * 50)
        print("[Workflow Result]")
        print(f"订单：{state.order_id}")
        print(f"状态：{state.current_step}")
        print(f"是否超时：{state.is_overdue}")
        print(f"工单：{state.ticket_id}")
        print(f"错误：{state.error}")
        print("=" * 50)
        print()

        return

    # 需要人工审批时进入 HITL
    print()
    print("=" * 50)
    print("需要人工审批")
    print("=" * 50)
    print(f"订单：{state.order_id}")
    print(f"动作：{state.approval_action}")
    print(f"原因：{state.approval_reason}")
    print()
    print("approve  - 批准")
    print("reject   - 拒绝")
    print("=" * 50)

    while True:
        decision = input(
            "审批决定 > "
        ).strip().lower()

        if decision == "approve":
            state = approve_shipping_ticket(
                state,
            )
            save_approval_log(
                source="shipping_workflow",
                action="create_shipping_ticket",
                target_id=state.order_id,
                decision="approved",
                success=state.ticket_id is not None,
                message=(
                        f"ticket_id={state.ticket_id}"
                        if state.ticket_id
                        else "审批通过，但未生成工单。"
                ),
            )

            print()
            print("=" * 50)
            print("[HITL Result]")
            print(f"状态：{state.current_step}")
            print(f"审批：{state.approval_status}")
            print(f"工单：{state.ticket_id}")
            print("=" * 50)
            print()

            return

        if decision == "reject":
            state = reject_shipping_ticket(
                state,
            )
            save_approval_log(
                source="shipping_workflow",
                action="create_shipping_ticket",
                target_id=state.order_id,
                decision="rejected",
                success=False,
                message="人工拒绝创建物流工单。",
            )

            print()
            print("=" * 50)
            print("[HITL Result]")
            print(f"状态：{state.current_step}")
            print(f"审批：{state.approval_status}")
            print("工单：未创建")
            print("=" * 50)
            print()

            return

        print("输入无效，请输入 approve 或 reject。")

def save_approval_log(
    source: str,
    action: str,
    target_id: str,
    decision: str,
    success: bool,
    message: str,
) -> None:
    """把一次人工审批结果追加保存到 JSONL。"""

    APPROVAL_LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "action": action,
        "target_id": target_id,
        "decision": decision,
        "success": success,
        "message": message,
    }

    with APPROVAL_LOG_PATH.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        )

def handle_agent_write_approval(
    request: dict,
) -> str:
    """处理普通 Agent 写操作的人工审批。"""

    action = request.get("action")

    print()
    print("=" * 50)
    print("Agent 写操作需要人工审批")
    print("=" * 50)

    if action == "create_ticket":
        order_id = request.get("order_id")
        issue_type = request.get("issue_type")
        description = request.get("description")

        if not order_id or not issue_type or not description:
            return "审批请求数据不完整，未执行创建工单。"

        print("动作：创建工单")
        print(f"订单：{order_id}")
        print(f"问题类型：{issue_type}")
        print(f"描述：{description}")

    elif action == "update_ticket_status":
        ticket_id = request.get("ticket_id")
        old_status = request.get("old_status")
        new_status = request.get("new_status")

        if not ticket_id or not new_status:
            return "审批请求数据不完整，未执行状态修改。"

        print("动作：修改工单状态")
        print(f"工单：{ticket_id}")
        print(f"原状态：{old_status}")
        print(f"新状态：{new_status}")

    else:
        return "未知审批动作，未执行任何写操作。"

    print()
    print("approve  - 批准")
    print("reject   - 拒绝")
    print("=" * 50)

    while True:
        decision = input(
            "审批决定 > "
        ).strip().lower()

        # 人工拒绝
        if decision == "reject":
            target_id = (
                request.get("order_id")
                or request.get("ticket_id")
                or "unknown"
            )

            save_approval_log(
                source="agent_tool",
                action=action,
                target_id=target_id,
                decision="rejected",
                success=False,
                message="人工拒绝该写操作。",
            )

            return (
                "人工已拒绝该写操作，"
                "未修改任何数据。"
            )

        if decision != "approve":
            print("输入无效，请输入 approve 或 reject。")
            continue

        # 创建工单
        if action == "create_ticket":
            ticket_id = create_ticket_in_db(
                order_id=request["order_id"],
                issue_type=request["issue_type"],
                description=request["description"],
            )

            formatted_ticket_id = f"T{ticket_id:04d}"

            save_approval_log(
                source="agent_tool",
                action="create_ticket",
                target_id=request["order_id"],
                decision="approved",
                success=True,
                message=f"ticket_id={formatted_ticket_id}",
            )

            return (
                "人工审批通过，"
                f"工单创建成功：{formatted_ticket_id}"
            )

        # 修改工单状态
        if action == "update_ticket_status":
            raw_ticket_id = request["ticket_id"]

            numeric_part = raw_ticket_id[1:]

            if not numeric_part.isdigit():
                save_approval_log(
                    source="agent_tool",
                    action="update_ticket_status",
                    target_id=raw_ticket_id,
                    decision="approved",
                    success=False,
                    message="工单号格式不正确。",
                )

                return (
                    "工单号格式不正确，"
                    "未执行状态修改。"
                )

            success = update_ticket_status_in_db(
                int(numeric_part),
                request["new_status"],
            )

            if success:
                save_approval_log(
                    source="agent_tool",
                    action="update_ticket_status",
                    target_id=raw_ticket_id,
                    decision="approved",
                    success=True,
                    message=(
                        f"new_status={request['new_status']}"
                    ),
                )

                return (
                    "人工审批通过，"
                    f"{raw_ticket_id} "
                    f"已更新为 "
                    f"{request['new_status']}。"
                )

            save_approval_log(
                source="agent_tool",
                action="update_ticket_status",
                target_id=raw_ticket_id,
                decision="approved",
                success=False,
                message="审批通过，但数据库更新失败。",
            )

            return "工单状态更新失败。"

async def main() -> None:
    """SupportPilot 主程序。"""

    init_db()

    conversation = []

    print(
        "SupportPilot 已启动。输入 exit 退出。"
    )
    print()

    while True:
        user_input = input(
            "你："
        ).strip()

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("SupportPilot 已退出。")
            break

        # 开发测试命令
        # 示例：/shipping A1004
        if user_input.startswith(
            "/shipping "
        ):
            order_id = user_input.replace(
                "/shipping ",
                "",
                1,
            ).strip().upper()

            if not re.fullmatch(
                r"A\d+",
                order_id,
            ):
                print()
                print(
                    "SupportPilot："
                    "订单号格式不正确，"
                    "例如 A1004。"
                )
                print()

                continue

            handle_shipping_workflow(
                order_id,
            )

            continue

        # 自然语言触发物流异常 Workflow
        if should_run_shipping_workflow(
            user_input
        ):
            order_id = extract_order_id(
                user_input
            )

            if order_id is None:
                print()
                print(
                    "SupportPilot："
                    "请提供订单号，"
                    "例如 A1004。"
                )
                print()

                continue

            handle_shipping_workflow(
                order_id,
            )

            continue

        try:
            chat_result = await process_chat_message(
                message=user_input,
                conversation=conversation,
            )

        except Exception as exc:
            print()
            print(
                "SupportPilot："
                f"处理请求时发生错误：{exc}"
            )
            print()

            continue

        answer = chat_result.answer

        if chat_result.approval_request is not None:
            # CLI 继续使用交互式审批，Web API 会返回待审批结构。
            answer = handle_agent_write_approval(
                chat_result.approval_request
            )

        # 无论是否需要审批，都必须最终输出一次结果
        print()
        print(
            f"SupportPilot：{answer}"
        )
        print()

        conversation = chat_result.conversation
        conversation[-1] = {
            "role": "assistant",
            "content": answer,
        }


if __name__ == "__main__":
    asyncio.run(
        main()
    )

from agents import function_tool
from supportpilot.db import (
    create_ticket_in_db,
    get_order_from_db,
    get_ticket_from_db,
    update_ticket_status_in_db,
)

WRITE_APPROVAL_PREFIX = "[APPROVAL_REQUIRED]"

@function_tool
def create_ticket(
    order_id: str,
    issue_type: str,
    description: str,
) -> str:
    """创建工单前先请求人工审批。"""

    order_id = order_id.strip().upper()
    issue_type = issue_type.strip()
    description = description.strip()

    if not order_id:
        return "缺少订单号。"

    if not issue_type:
        return "缺少问题类型。"

    if not description:
        return "缺少问题描述。"

    order = get_order_from_db(order_id)

    if order is None:
        return f"未找到订单 {order_id}。"

    return (
        f"{WRITE_APPROVAL_PREFIX}\n"
        f"action=create_ticket\n"
        f"order_id={order_id}\n"
        f"issue_type={issue_type}\n"
        f"description={description}"
    )


@function_tool
def get_ticket_status(ticket_id: str) -> str:
    """根据工单编号查询售后工单状态。"""

    print(f"\n[Tool] 收到工单查询请求：{ticket_id}")

    ticket_id = ticket_id.strip().upper()

    if not ticket_id:
        return "工单编号不能为空。"

    if not ticket_id.startswith("T"):
        return "工单编号格式不正确，请提供类似 T0001 的工单编号。"

    number_part = ticket_id[1:]

    if not number_part.isdigit():
        return "工单编号格式不正确，请提供类似 T0001 的工单编号。"

    ticket_number = int(number_part)

    ticket = get_ticket_from_db(ticket_number)

    if ticket is None:
        result = "未找到该工单，请检查工单编号是否正确。"
        print(f"[Tool] 查询结果：{result}")
        return result

    display_ticket_id = f"T{ticket['ticket_id']:04d}"

    result = (
        f"工单编号：{display_ticket_id}\n"
        f"订单号：{ticket['order_id']}\n"
        f"问题类型：{ticket['issue_type']}\n"
        f"问题描述：{ticket['description']}\n"
        f"工单状态：{ticket['status']}"
    )

    print(f"[Tool] 查询结果：\n{result}")

    return result


@function_tool
def update_ticket_status(
    ticket_id: str,
    new_status: str,
) -> str:
    """修改工单状态前先请求人工审批。"""

    ticket_id = ticket_id.strip().upper()
    new_status = new_status.strip()

    allowed_status = [
        "已创建",
        "处理中",
        "已解决",
    ]

    if not ticket_id.startswith("T"):
        return "工单号格式不正确，例如 T0001。"

    if new_status not in allowed_status:
        return (
            "状态不合法，可选状态："
            "已创建、处理中、已解决。"
        )

    numeric_id = ticket_id[1:]

    if not numeric_id.isdigit():
        return "工单号格式不正确，例如 T0001。"

    ticket = get_ticket_from_db(
        int(numeric_id)
    )

    if ticket is None:
        return f"未找到工单 {ticket_id}。"

    return (
        f"{WRITE_APPROVAL_PREFIX}\n"
        f"action=update_ticket_status\n"
        f"ticket_id={ticket_id}\n"
        f"old_status={ticket['status']}\n"
        f"new_status={new_status}"
    )
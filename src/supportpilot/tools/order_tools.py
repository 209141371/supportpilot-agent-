from agents import function_tool

from supportpilot.db import get_order_from_db, list_orders_from_db


@function_tool
def get_order_status(order_id: str) -> str:
    """根据订单号查询订单详情。"""

    print(f"\n[Tool] 收到订单查询请求：{order_id}")

    order_id = order_id.strip().upper()

    if not order_id:
        return "订单号不能为空。"

    if not order_id.startswith("A"):
        return "订单号格式不正确，请提供类似 A1001 的订单号。"

    order = get_order_from_db(order_id)

    if order is None:
        result = "未找到该订单，请检查订单号是否正确。"
        print(f"[Tool] 查询结果：{result}")
        return result

    result = (
        f"订单号：{order['order_id']}\n"
        f"客户：{order['customer_name']}\n"
        f"商品：{order['product_name']}\n"
        f"支付状态：{order['payment_status']}\n"
        f"物流状态：{order['shipping_status']}\n"
        f"预计送达：{order['estimated_delivery']}"
    )

    print(f"[Tool] 查询结果：\n{result}")

    return result


@function_tool
def get_logistics_order_summary() -> str:
    """查询系统中全部物流订单的数量和当前物流状态汇总。"""

    orders = list_orders_from_db()

    if not orders:
        return "当前系统没有物流订单。"

    status_counts: dict[str, int] = {}

    for order in orders:
        status = order["shipping_status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    lines = [f"当前系统共有 {len(orders)} 个物流订单。", "物流状态汇总："]
    lines.extend(
        f"- {status}：{count} 个"
        for status, count in status_counts.items()
    )
    lines.append("订单明细：")
    lines.extend(
        f"- {order['order_id']}：{order['shipping_status']}"
        for order in orders
    )

    return "\n".join(lines)

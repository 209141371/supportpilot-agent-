import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT_DIR),
)


from run import (
    extract_order_id,
    should_run_shipping_workflow,
)
from eval_logging import log_eval_failure


CASES_PATH = ROOT_DIR / "evals" / "route_cases.jsonl"

MIN_ROUTE_ACCURACY = 1.0


def load_cases() -> list[dict]:
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


def decide_route(
    text: str,
) -> tuple[str, str | None]:
    """按照 run.py 当前逻辑计算路由结果。"""

    is_shipping = should_run_shipping_workflow(
        text
    )

    order_id = extract_order_id(
        text
    )

    if not is_shipping:
        return "agent", order_id

    if order_id is None:
        return "shipping_missing_order", None

    return "shipping_workflow", order_id


def evaluate_case(
    case: dict,
) -> bool:
    """评估单条路由测试用例。"""

    query = case["query"]

    expected_route = case[
        "expected_route"
    ]

    expected_order_id = case[
        "expected_order_id"
    ]

    actual_route, actual_order_id = decide_route(
        query
    )

    route_passed = (
        actual_route
        == expected_route
    )

    order_id_passed = (
        actual_order_id
        == expected_order_id
    )

    # 先计算 passed
    passed = (
        route_passed
        and order_id_passed
    )

    # 再使用 passed 判断是否记录失败
    if not passed:
        log_eval_failure(
            suite="intent_route",
            case=query,
            expected={
                "route": expected_route,
                "order_id": expected_order_id,
            },
            actual={
                "route": actual_route,
                "order_id": actual_order_id,
            },
            details={
                "route_passed": route_passed,
                "order_id_passed": order_id_passed,
            },
        )

    print()
    print("-" * 50)
    print(f"Query: {query}")
    print(
        f"Expected route: {expected_route}"
    )
    print(
        f"Actual route:   {actual_route}"
    )
    print(
        f"Expected order_id: {expected_order_id}"
    )
    print(
        f"Actual order_id:   {actual_order_id}"
    )
    print(
        f"Result: {'PASS' if passed else 'FAIL'}"
    )

    return passed


def main() -> None:
    cases = load_cases()

    passed_count = 0

    for case in cases:
        if evaluate_case(case):
            passed_count += 1

    total_count = len(cases)

    accuracy = (
        passed_count / total_count
        if total_count
        else 0
    )

    print()
    print("=" * 50)
    print("Intent Route Eval Summary")
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
    print("Route Quality Gate")
    print("=" * 50)

    if accuracy >= MIN_ROUTE_ACCURACY:
        print("Status: PASS")
    else:
        print("Status: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
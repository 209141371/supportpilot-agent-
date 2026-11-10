import json
import sys
from pathlib import Path
from eval_logging import log_eval_failure

MIN_WORKFLOW_ACCURACY = 1.0

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(
    0,
    str(SRC_DIR),
)


from supportpilot.db import init_db
from supportpilot.workflows.shipping_workflow import run_shipping_workflow


CASES_PATH = ROOT_DIR / "evals" / "workflow_cases.jsonl"


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


def evaluate_case(case: dict) -> bool:
    order_id = case["order_id"]

    state = run_shipping_workflow(
        order_id,
    )

    actual_has_ticket = (
        state.ticket_created
        or state.ticket_reused
        or state.ticket_id is not None
    )

    checks = {
        "order_found": (
            state.order_found
            == case["expected_order_found"]
        ),
        "is_overdue": (
            state.is_overdue
            == case["expected_overdue"]
        ),
        "has_ticket": (
            actual_has_ticket
            == case["expected_ticket"]
        ),
    }

    passed = all(
        checks.values()
    )
    if not passed:
        log_eval_failure(
        suite="workflow",
        case=order_id,
        expected={
            "order_found": case["expected_order_found"],
            "is_overdue": case["expected_overdue"],
            "has_ticket": case["expected_ticket"],
        },
        actual={
            "order_found": state.order_found,
            "is_overdue": state.is_overdue,
            "has_ticket": actual_has_ticket,
            "current_step": state.current_step,
        },
        details={
            "error": state.error,
        },
    )

    print()
    print("-" * 50)
    print(f"Case: {order_id}")
    print(
        f"order_found: "
        f"expected={case['expected_order_found']}, "
        f"actual={state.order_found}"
    )
    print(
        f"is_overdue: "
        f"expected={case['expected_overdue']}, "
        f"actual={state.is_overdue}"
    )
    print(
        f"has_ticket: "
        f"expected={case['expected_ticket']}, "
        f"actual={actual_has_ticket}"
    )
    print(
        f"current_step: {state.current_step}"
    )
    print(
        f"result: {'PASS' if passed else 'FAIL'}"
    )

    return passed


def main() -> None:
    init_db()

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
    print("Workflow Eval Summary")
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
    print("Workflow Quality Gate")
    print("=" * 50)

    if accuracy >= MIN_WORKFLOW_ACCURACY:
        print("Status: PASS")
    else:
        print("Status: FAIL")
        sys.exit(1)

if __name__ == "__main__":
    main()
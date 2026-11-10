import json
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

FAILURE_LOG_PATH = (
    ROOT_DIR
    / "data"
    / "logs"
    / "eval_failures.jsonl"
)


def log_eval_failure(
    suite: str,
    case: str,
    expected,
    actual,
    details: dict | None = None,
) -> None:
    """记录一条 Eval 失败案例。"""

    FAILURE_LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "timestamp": datetime.now().isoformat(),
        "suite": suite,
        "case": case,
        "expected": expected,
        "actual": actual,
        "details": details or {},
    }

    with FAILURE_LOG_PATH.open(
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
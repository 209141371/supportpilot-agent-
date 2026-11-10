import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

REGRESSION_LOG_PATH = (
    ROOT_DIR
    / "data"
    / "logs"
    / "eval_regression.jsonl"
)

FAILURE_LOG_PATH = (
    ROOT_DIR
    / "data"
    / "logs"
    / "eval_failures.jsonl"
)

EVAL_REPORT_PATH = (
    ROOT_DIR
    / "evals"
    / "eval_report.md"
)

RELEASE_GATE_REQUIRED_SUITES = 5

EVAL_SCRIPTS = [
    {
        "name": "RAG Eval",
        "path": ROOT_DIR / "evals" / "run_rag_eval.py",
    },
    {
        "name": "Workflow Eval",
        "path": ROOT_DIR / "evals" / "run_workflow_eval.py",
    },
    {
        "name": "HITL Eval",
        "path": ROOT_DIR / "evals" / "run_hitl_eval.py",
    },
    {
        "name": "Agent Tool Eval",
        "path": ROOT_DIR / "evals" / "run_agent_tool_eval.py",
    },
    {
        "name": "Intent Route Eval",
        "path": ROOT_DIR / "evals" / "run_route_eval.py",
    },
]


def extract_percentage(
    output: str,
    label: str,
) -> str | None:
    """从 Eval 输出中提取百分比指标。"""

    pattern = (
        re.escape(label)
        + r".*?(\d+(?:\.\d+)?%)"
    )

    match = re.search(
        pattern,
        output,
        re.IGNORECASE,
    )

    if match is None:
        return None

    return match.group(1)


def extract_fraction(
    output: str,
    label: str,
) -> str | None:
    """从 Eval 输出中提取类似 4/4 的通过数量。"""

    pattern = (
        re.escape(label)
        + r".*?(\d+/\d+)"
    )

    match = re.search(
        pattern,
        output,
        re.IGNORECASE,
    )

    if match is None:
        return None

    return match.group(1)


def extract_metrics(
    name: str,
    output: str,
) -> dict:
    """根据不同 Eval Suite 提取关键指标。"""

    metrics = {}

    if name == "RAG Eval":
        metrics["Top1 Accuracy"] = (
            extract_percentage(
                output,
                "Top1 Accuracy",
            )
        )

        metrics["Recall@3"] = (
            extract_percentage(
                output,
                "Recall@3",
            )
        )

        metrics["No-answer Accuracy"] = (
            extract_percentage(
                output,
                "No-answer Accuracy",
            )
        )

    else:
        metrics["Passed"] = (
            extract_fraction(
                output,
                "Passed",
            )
        )

        metrics["Accuracy"] = (
            extract_percentage(
                output,
                "Accuracy",
            )
        )

    return {
        key: value
        for key, value in metrics.items()
        if value is not None
    }


def run_eval(
    name: str,
    path: Path,
) -> dict:
    """运行单个 Eval，并返回结构化结果。"""

    print()
    print("=" * 60)
    print(f"Running: {name}")
    print("=" * 60)

    result = subprocess.run(
        [
            sys.executable,
            str(path),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout:
        print(
            result.stdout,
            end="",
        )

    if result.stderr:
        print(
            result.stderr,
            end="",
        )

    passed = (
        result.returncode == 0
    )

    metrics = extract_metrics(
        name=name,
        output=result.stdout,
    )

    print()
    print(
        f"{name}: "
        f"{'PASS' if passed else 'FAIL'}"
    )

    return {
        "name": name,
        "passed": passed,
        "returncode": result.returncode,
        "metrics": metrics,
    }


def save_regression_report(
    results: list[dict],
    timestamp: str,
) -> None:
    """保存一次完整回归测试结果。"""

    REGRESSION_LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_count = len(results)

    passed_count = sum(
        1
        for item in results
        if item["passed"]
    )

    failed_count = (
        total_count - passed_count
    )

    overall_passed = (
        failed_count == 0
    )

    record = {
        "timestamp": timestamp,
        "total_suites": total_count,
        "passed_suites": passed_count,
        "failed_suites": failed_count,
        "overall_status": (
            "PASS"
            if overall_passed
            else "FAIL"
        ),
        "suites": results,
    }

    with REGRESSION_LOG_PATH.open(
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


def count_failure_records() -> int:
    """统计历史 Failure Case 数量。"""

    if not FAILURE_LOG_PATH.exists():
        return 0

    count = 0

    with FAILURE_LOG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            if line.strip():
                count += 1

    return count


def format_metrics(
    metrics: dict,
) -> str:
    """把指标字典格式化成 Markdown 文本。"""

    if not metrics:
        return "-"

    parts = []

    for key, value in metrics.items():
        parts.append(
            f"{key}: {value}"
        )

    return "<br>".join(parts)


def evaluate_release_gate(
    results: list[dict],
) -> tuple[bool, list[str]]:
    """判断当前版本是否满足发布门槛。"""

    reasons = []

    if len(results) != RELEASE_GATE_REQUIRED_SUITES:
        reasons.append(
            (
                "Eval Suite 数量不符合预期："
                f"{len(results)}/"
                f"{RELEASE_GATE_REQUIRED_SUITES}"
            )
        )

    for item in results:
        if not item["passed"]:
            reasons.append(
                f"{item['name']} 未通过 Quality Gate"
            )

    release_ready = (
        len(reasons) == 0
    )

    return release_ready, reasons

def generate_markdown_report(
    results: list[dict],
    timestamp: str,
) -> None:
    """生成面向人的 Markdown Eval Report。"""

    total_count = len(results)

    passed_count = sum(
        1
        for item in results
        if item["passed"]
    )

    failed_count = (
        total_count - passed_count
    )

    overall_status = (
        "PASS"
        if failed_count == 0
        else "FAIL"
    )

    failure_record_count = (
        count_failure_records()
    )

    release_ready, release_reasons = (
        evaluate_release_gate(
            results
    )
)

    lines = []

    lines.append(
        "# SupportPilot Evaluation Report"
    )
    lines.append("")

    lines.append(
        f"- Generated at: `{timestamp}`"
    )

    lines.append(
        f"- Overall Status: **{overall_status}**"
    )

    lines.append(
        "- Release Gate: "
        f"**{'READY' if release_ready else 'NOT READY'}**"
)

    lines.append(
        f"- Eval Suites Passed: **{passed_count}/{total_count}**"
    )

    lines.append(
        f"- Historical Failure Records: **{failure_record_count}**"
    )

    lines.append("")

    lines.append("")

    lines.append(
    "## Release Gate"
    )

    lines.append("")

    if release_ready:
        lines.append(
        "Current version satisfies all defined regression quality gates."
    )
    else:
        lines.append(
        "Current version does not satisfy the release gate."
    )

        lines.append("")

    for reason in release_reasons:
        lines.append(
            f"- {reason}"
        )

    lines.append("")

    lines.append(
        "## Evaluation Summary"
    )
    lines.append("")

    lines.append(
        "| Eval Suite | Status | Metrics |"
    )

    lines.append(
        "|---|---|---|"
    )

    for item in results:
        status = (
            "PASS"
            if item["passed"]
            else "FAIL"
        )

        metrics_text = format_metrics(
            item.get(
                "metrics",
                {},
            )
        )

        lines.append(
            f"| {item['name']} "
            f"| {status} "
            f"| {metrics_text} |"
        )

    lines.append("")

    lines.append(
        "## Quality Dimensions"
    )
    lines.append("")

    lines.append(
        "- **RAG Eval**: validates retrieval ranking, Recall@3, and no-answer behavior."
    )

    lines.append(
        "- **Workflow Eval**: validates deterministic shipping workflow behavior."
    )

    lines.append(
        "- **HITL Eval**: validates approval safety rules for database write operations."
    )

    lines.append(
        "- **Agent Tool Eval**: validates whether the Agent selects the expected Tool."
    )

    lines.append(
        "- **Intent Route Eval**: validates routing between the Shipping Workflow and the normal Agent path."
    )

    lines.append("")

    lines.append(
        "## Failed Suites"
    )
    lines.append("")

    failed_results = [
        item
        for item in results
        if not item["passed"]
    ]

    if not failed_results:
        lines.append(
            "No Eval Suite failed in this regression run."
        )
    else:
        for item in failed_results:
            lines.append(
                f"- {item['name']} "
                f"(return code: {item['returncode']})"
            )

    lines.append("")

    lines.append(
        "## Evaluation Notes"
    )
    lines.append("")

    lines.append(
        "These evaluations are small controlled regression and smoke-test suites."
    )

    lines.append(
        "A PASS result means the current implementation satisfies the defined test cases and quality gates; it should not be interpreted as production-level accuracy or safety."
    )

    lines.append("")

    lines.append(
        "Failure cases are recorded separately in:"
    )

    lines.append("")

    lines.append(
        "`data/logs/eval_failures.jsonl`"
    )

    lines.append("")

    lines.append(
        "Regression history is recorded in:"
    )

    lines.append("")

    lines.append(
        "`data/logs/eval_regression.jsonl`"
    )

    EVAL_REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    EVAL_REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    timestamp = datetime.now().isoformat()

    results = []

    for eval_config in EVAL_SCRIPTS:
        result = run_eval(
            name=eval_config["name"],
            path=eval_config["path"],
        )

        results.append(
            result
        )

    passed_count = sum(
        1
        for item in results
        if item["passed"]
    )

    total_count = len(results)

    overall_passed = (
        passed_count == total_count
    )

    release_ready, release_reasons = (
        evaluate_release_gate(
            results
    )
)

    print()
    print("=" * 60)
    print("SupportPilot Eval Summary")
    print("=" * 60)

    print(
        f"Eval Suites Passed: "
        f"{passed_count}/{total_count}"
    )

    if overall_passed:
        print("Overall Status: PASS")
    else:
        print("Overall Status: FAIL")

        print(
            "Release Gate: "
             f"{'READY' if release_ready else 'NOT READY'}"
)

    save_regression_report(
        results=results,
        timestamp=timestamp,
    )

    generate_markdown_report(
        results=results,
        timestamp=timestamp,
    )

    print()
    print(
        "Eval report generated:"
    )
    print(
        EVAL_REPORT_PATH
    )

    if not release_ready:
        sys.exit(1)


if __name__ == "__main__":
    main()
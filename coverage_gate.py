#!/usr/bin/env python3
"""Coverage quality gate helper for local hooks and CI pipelines."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import xml.etree.ElementTree as ET


def read_current_coverage(coverage_xml_path: pathlib.Path) -> float:
    if not coverage_xml_path.exists():
        raise FileNotFoundError(f"Coverage report not found: {coverage_xml_path}")

    content = coverage_xml_path.read_bytes()
    # A real coverage.xml never declares a DTD; refusing it blocks entity-expansion
    # attacks (billion laughs) without needing a third-party XML parser.
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise ValueError(f"DTD/entity declarations are not allowed in: {coverage_xml_path}")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML in {coverage_xml_path}: {exc}") from exc

    line_rate = root.get("line-rate")
    if line_rate is None:
        raise ValueError(f"line-rate attribute not found in: {coverage_xml_path}")

    try:
        return float(line_rate) * 100.0
    except ValueError as exc:
        raise ValueError(f"Invalid line-rate '{line_rate}' in: {coverage_xml_path}") from exc


def read_baseline(baseline_path: pathlib.Path) -> float:
    if not baseline_path.exists():
        raise ValueError(f"Baseline file not found: {baseline_path}")

    content = baseline_path.read_text(encoding="utf-8").strip()

    try:
        return float(content)
    except ValueError as exc:
        raise ValueError(f"Invalid baseline value '{content}' in: {baseline_path}") from exc


def write_github_outputs(current: float, baseline: float, status: str) -> None:
    """Expose results to GitHub Actions (step outputs and job summary), when available."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"current={current:.2f}\n")
            f.write(f"baseline={baseline:.2f}\n")
            f.write(f"delta={current - baseline:+.2f}\n")
            f.write(f"status={status}\n")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        icon = {"fail": "❌", "ok": "✅", "improved": "🚀"}[status]
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("### Coverage gate\n\n")
            f.write("| Baseline | Current | Delta | Status |\n")
            f.write("|---:|---:|---:|:---:|\n")
            f.write(f"| {baseline:.2f}% | {current:.2f}% | {current - baseline:+.2f} pp | {icon} {status} |\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Coverage quality gate: compare current coverage against a stored baseline.",
    )
    parser.add_argument(
        "--coverage-xml",
        default="coverage.xml",
        metavar="PATH",
        help="Path to the coverage.xml report (default: coverage.xml)",
    )
    parser.add_argument(
        "--baseline",
        default=".coverage-baseline",
        metavar="PATH",
        help="Path to the baseline file (default: .coverage-baseline)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Never rewrite the baseline file, even when coverage improves (recommended for CI)",
    )
    args = parser.parse_args(argv)

    coverage_xml_path = pathlib.Path(args.coverage_xml)
    baseline_path = pathlib.Path(args.baseline)

    try:
        current = read_current_coverage(coverage_xml_path)
        baseline = read_baseline(baseline_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[coverage-gate] ERROR: {exc}")
        return 1

    # Compare at the same precision the baseline is stored (2 decimals), so that
    # float noise (e.g. 85.00000000000001) cannot cause a spurious regression.
    current = round(current, 2)

    if current < baseline:
        print(f"[coverage-gate] FAIL: coverage regressed from {baseline:.2f}% to {current:.2f}%")
        write_github_outputs(current, baseline, "fail")
        return 1

    if current == baseline:
        print(f"[coverage-gate] OK: coverage unchanged (baseline {baseline:.2f}%).")
        write_github_outputs(current, baseline, "ok")
        return 0

    if args.check_only:
        print(f"[coverage-gate] SUCC: coverage improved from {baseline:.2f}% to {current:.2f}% (baseline not updated)")
    else:
        print(f"[coverage-gate] SUCC: coverage improved from {baseline:.2f}% to {current:.2f}%")
        baseline_path.write_text(f"{current:.2f}\n", encoding="utf-8")
    write_github_outputs(current, baseline, "improved")

    return 0


if __name__ == "__main__":
    sys.exit(main())

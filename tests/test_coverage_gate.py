import pathlib

import pytest

import coverage_gate


def _xml(tmp_path: pathlib.Path, line_rate: str = "0.85") -> pathlib.Path:
    path = tmp_path / "coverage.xml"
    path.write_text(
        f'<?xml version="1.0" ?>\n<coverage version="7.0" line-rate="{line_rate}" branch-rate="0">\n</coverage>\n',
        encoding="utf-8",
    )
    return path


def _baseline(tmp_path: pathlib.Path, value: str) -> pathlib.Path:
    path = tmp_path / ".coverage-baseline"
    path.write_text(f"{value}\n", encoding="utf-8")
    return path


def _run(xml: pathlib.Path, baseline: pathlib.Path, *extra: str) -> int:
    return coverage_gate.main(["--coverage-xml", str(xml), "--baseline", str(baseline), *extra])


def test_read_current_coverage_parses_line_rate(tmp_path):
    assert coverage_gate.read_current_coverage(_xml(tmp_path, "0.855")) == pytest.approx(85.5)


def test_read_current_coverage_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        coverage_gate.read_current_coverage(tmp_path / "nope.xml")


def test_read_current_coverage_without_line_rate(tmp_path):
    path = tmp_path / "coverage.xml"
    path.write_text("<coverage></coverage>", encoding="utf-8")
    with pytest.raises(ValueError, match="line-rate"):
        coverage_gate.read_current_coverage(path)


def test_read_current_coverage_rejects_entities(tmp_path):
    path = tmp_path / "coverage.xml"
    path.write_text('<!DOCTYPE a [<!ENTITY x "y">]><coverage line-rate="1"/>', encoding="utf-8")
    with pytest.raises(ValueError, match="not allowed"):
        coverage_gate.read_current_coverage(path)


def test_read_baseline_invalid_value(tmp_path):
    with pytest.raises(ValueError, match="Invalid baseline"):
        coverage_gate.read_baseline(_baseline(tmp_path, "abc"))


def test_regression_fails(tmp_path, capsys):
    assert _run(_xml(tmp_path, "0.79"), _baseline(tmp_path, "85.50")) == 1
    assert "FAIL" in capsys.readouterr().out


def test_equal_passes_and_keeps_baseline(tmp_path):
    baseline = _baseline(tmp_path, "85.00")
    assert _run(_xml(tmp_path, "0.85"), baseline) == 0
    assert baseline.read_text() == "85.00\n"


def test_float_noise_is_not_a_regression(tmp_path):
    assert _run(_xml(tmp_path, "0.8500000000000001"), _baseline(tmp_path, "85.00")) == 0


def test_improvement_updates_baseline(tmp_path):
    baseline = _baseline(tmp_path, "80.00")
    assert _run(_xml(tmp_path, "0.855"), baseline) == 0
    assert baseline.read_text() == "85.50\n"


def test_improvement_with_check_only_keeps_baseline(tmp_path):
    baseline = _baseline(tmp_path, "80.00")
    assert _run(_xml(tmp_path, "0.855"), baseline, "--check-only") == 0
    assert baseline.read_text() == "80.00\n"


def test_missing_baseline_is_error(tmp_path, capsys):
    assert _run(_xml(tmp_path), tmp_path / "missing") == 1
    assert "ERROR" in capsys.readouterr().out


def test_github_outputs_and_summary(tmp_path, monkeypatch):
    out, summary = tmp_path / "out", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert _run(_xml(tmp_path, "0.855"), _baseline(tmp_path, "80.00"), "--check-only") == 0
    assert out.read_text().splitlines() == ["current=85.50", "baseline=80.00", "delta=+5.50", "status=improved"]
    assert "| 80.00% | 85.50% | +5.50 pp |" in summary.read_text()

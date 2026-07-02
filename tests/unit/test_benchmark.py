from dyor.benchmark import Case, DEFAULT_CASES, run_benchmark


def test_default_cases_all_pass():
    report = run_benchmark(DEFAULT_CASES)
    assert report.ok, [r.reasons for r in report.results if not r.passed]
    assert report.accuracy == 1.0


def test_report_counts():
    report = run_benchmark(DEFAULT_CASES)
    assert report.total == len(DEFAULT_CASES)
    assert report.passed == report.total


def test_wrong_expectation_fails():
    # a dead token expected NOT to be zeroed should fail the benchmark
    bad = Case("dead", DEFAULT_CASES[2].record, expect_zeroed=False)
    report = run_benchmark([bad, *DEFAULT_CASES[:1]])
    dead = next(r for r in report.results if r.name == "dead")
    assert not dead.passed
    assert any("zeroed" in reason for reason in dead.reasons)

"""Fixed rubric independent of the chosen procedure and model output."""
from .tools import CHECKS, issue

RUBRIC = "research-quality-v1"


def evaluate(case, report, errors):
    expected = {c for c in CHECKS if issue(c, case)}
    observed = set(report.get('warnings', []))
    expected_growth = (None if expected & {"comparability", "denominator"} else
                       round((case['revenue'] / case['previous_revenue'] - 1) * 100, 6))
    metrics = {c: (c in expected) == (c in observed) for c in CHECKS}
    metrics['calculation'] = 'growth_pct' in report and report['growth_pct'] == expected_growth
    metrics['execution'] = not errors and bool(report)
    metrics['provenance'] = all(report.get(k) == case[k] for k in ('source', 'period', 'as_of', 'synthetic'))
    return {"rubric": RUBRIC, "metrics": metrics,
            "score": sum(metrics.values()) / len(metrics),
            "failures": [k for k, passed in metrics.items() if not passed]}


def regression_cases():
    """Synthetic fixed suite; never fed to the proposal generator as experience."""
    base = dict(ticker="TEST", as_of="2026-01-01", period="2025-06-30", revenue=120,
                previous_revenue=100, source="fixture://verified", comparable=True, synthetic=True)
    variants = [{}, {"source": ""}, {"period": "2020-01-01"}, {"comparable": False},
                {"previous_revenue": 0}, {"previous_revenue": -10},
                {"period": "2027-01-01"}, {"source": "", "comparable": False}]
    return [dict(base, **v) for v in variants]

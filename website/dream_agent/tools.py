import math
from datetime import date


CHECKS = ("source", "freshness", "comparability", "denominator")
LESSONS = {
    "source": "Tandai angka tanpa provenance sebagai data tidak terverifikasi.",
    "freshness": "Periksa tanggal laporan terhadap tanggal riset; tandai data usang.",
    "comparability": "Jangan membandingkan periode dengan cakupan bisnis berbeda.",
    "denominator": "Jangan menghitung pertumbuhan dari basis nol atau negatif.",
}


def validate_case(case):
    required = {"ticker", "as_of", "period", "revenue", "previous_revenue", "source", "comparable", "synthetic"}
    if not isinstance(case, dict) or not required <= case.keys():
        raise ValueError("Dataset is missing required fields")
    date.fromisoformat(case['as_of'])
    date.fromisoformat(case['period'])
    for key in ("revenue", "previous_revenue"):
        if type(case[key]) not in (int, float) or not math.isfinite(case[key]):
            raise ValueError(f"Invalid numeric field: {key}")
    if type(case['comparable']) is not bool or type(case['synthetic']) is not bool:
        raise ValueError("comparable and synthetic must be booleans")
    if not isinstance(case['source'], str) or not isinstance(case['ticker'], str):
        raise ValueError("source and ticker must be strings")
    return case


def issue(check, case):
    if check == "source":
        return not case['source'].strip()
    if check == "freshness":
        age = (date.fromisoformat(case['as_of']) - date.fromisoformat(case['period'])).days
        return age > 550 or age < 0
    if check == "comparability":
        return not case['comparable']
    if check == "denominator":
        return case['previous_revenue'] <= 0
    raise ValueError("Unknown check")


class ResearchTools:
    """Closed tool registry: no shell, trading, URL fetch, or arbitrary file reads."""
    def execute(self, step, case, context):
        if step == "load_evidence":
            context['evidence'] = validate_case(case).copy()
            return context['evidence']
        if step in CHECKS:
            flagged = issue(step, context['evidence'])
            if flagged:
                context['warnings'].append(step)
            return {"check": step, "flagged": flagged}
        if step == "calculate":
            evidence = context['evidence']
            blocked = set(context['warnings']) & {"comparability", "denominator"}
            # Baseline deliberately lacks procedural checks; zero still cannot crash calculation.
            context['growth_pct'] = (None if blocked or evidence['previous_revenue'] == 0 else
                round((evidence['revenue'] / evidence['previous_revenue'] - 1) * 100, 6))
            return {"growth_pct": context['growth_pct']}
        if step == "report":
            return {"ticker": case['ticker'], "synthetic": case['synthetic'],
                    "period": case['period'], "as_of": case['as_of'], "source": case['source'],
                    "growth_pct": context.get('growth_pct'), "warnings": list(context['warnings']),
                    "conclusion": "Observasi dataset terbatas; bukan rekomendasi beli/jual atau prediksi return."}
        raise ValueError(f"Tool not allowed: {step}")

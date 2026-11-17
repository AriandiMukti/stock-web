from .evaluation import evaluate
from .planner import RulePlanner, validate_plan
from .store import encode, now
from .tools import ResearchTools, validate_case


def execute(goal, case, procedure, planner=None):
    validate_case(case)
    if not goal.strip() or len(goal) > 8000:
        raise ValueError("Goal must contain 1..8000 characters")
    context = {'warnings': []}
    trace, errors, report, plan = [], [], {}, []
    try:
        plan = validate_plan((planner or RulePlanner()).plan(goal, procedure), procedure)
        tools = ResearchTools()
        for step in plan:
            result = tools.execute(step, case, context)
            trace.append({"tool": step, "result": result})
            if step == 'report':
                report = result
    except Exception as exc:
        errors.append({"type": type(exc).__name__, "message": str(exc)[:2000]})
    return {"goal": goal, "case": case, "plan": plan, "trace": trace, "errors": errors,
            "report": report, "evaluation": evaluate(case, report, errors), "time": now()}


def run(store, goal, case, planner=None):
    version, procedure = store.active()
    result = execute(goal, case, procedure, planner)
    result['version'] = version
    with store.transaction():
        cursor = store.db.execute("INSERT INTO runs(body) VALUES (?)", (encode(result),))
        result['id'] = cursor.lastrowid
        store.log("run_completed", {"run": result['id'], "version": version,
                                    "evaluation": result['evaluation'], "errors": result['errors']})
    return result

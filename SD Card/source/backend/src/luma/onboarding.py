"""Secret-free setup navigation; reviewed steps are never hardware-test passes."""
STEPS = ("welcome", "network", "space", "privacy", "extras", "calendar", "phone", "voice", "remote", "review")
OPTIONAL = ("extras", "calendar", "phone", "voice", "remote")


def load_progress(storage):
    raw = storage.get_cache("onboarding", "progress") or {}
    if not isinstance(raw, dict):
        raw = {}
    statuses = raw.get("statuses", {})
    if not isinstance(statuses, dict):
        statuses = {}
    return {"version": 1, "step": raw.get("step") if raw.get("step") in STEPS else "welcome",
            "statuses": {key: value for key, value in statuses.items()
                         if key in STEPS and value in ("reviewed", "later")}}


def transition(progress, payload):
    if not isinstance(payload, dict) or set(payload) - {"action", "step"}:
        raise ValueError("Invalid setup request")
    action, step = payload.get("action"), payload.get("step")
    if not isinstance(action, str) or action not in ("visit", "continue", "later", "skip_optional", "finish"):
        raise ValueError("Invalid setup request")
    if action in ("visit", "continue", "later"):
        if not isinstance(step, str) or step not in STEPS or (action == "later" and step not in OPTIONAL):
            raise ValueError("Invalid setup step")
    elif "step" in payload:
        raise ValueError("Unexpected setup step")
    result = {"version": 1, "step": progress["step"], "statuses": dict(progress["statuses"])}
    if action == "visit":
        result["step"] = step
    elif action in ("continue", "later"):
        if step != result["step"] or step == "review":
            raise ValueError("Refresh setup before continuing")
        result["statuses"][step] = "later" if action == "later" else "reviewed"
        result["step"] = STEPS[STEPS.index(step) + 1]
    elif action == "skip_optional":
        if result["step"] not in OPTIONAL:
            raise ValueError("Not on an optional step")
        for key in OPTIONAL[OPTIONAL.index(result["step"]):]:
            result["statuses"].setdefault(key, "later")
        result["step"] = "review"
    elif action == "finish":
        if result["step"] != "review":
            raise ValueError("Review setup before finishing")
        result["statuses"]["review"] = "reviewed"
    return result

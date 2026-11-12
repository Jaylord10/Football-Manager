# ai/decision_log.py
from ai.debug import DEBUG_DECISIONS, DEBUG_ONLY_TEAM

def print_decision(carrier, layer, action, target=None, score=None, notes=None):
    if not DEBUG_DECISIONS:
        return
    if DEBUG_ONLY_TEAM is not None and carrier.team != DEBUG_ONLY_TEAM:
        return

    name = getattr(carrier, "name", carrier.role)
    tgt = ""
    if target is not None:
        tgt_name = getattr(target, "name", str(target))
        tgt = f" -> {tgt_name}"

    s = ""
    if score is not None:
        s = f" score={round(float(score), 1)}"

    n = ""
    if notes:
        n = f" | {notes}"

    print(f"[DECISION] {name} ({carrier.role}) | {layer}:{action}{tgt}{s}{n}")

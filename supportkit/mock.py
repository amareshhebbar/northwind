from __future__ import annotations

import hashlib
import json
import re
from typing import List, Optional, Tuple

from supportkit.text import bm25_rank, coverage, overlap, token_set

INJECTION = re.compile(
    r"ignore (all |your |the )?(previous|prior|above)|system prompt|reveal your|jailbreak|developer mode|act as|pretend to be|you are now",
    re.I,
)
ESCALATE = re.compile(r"\b(lawyer|attorney|sue|lawsuit|legal action|court|regulator|media|press|threat)\b", re.I)
FABRICATIONS = [
    "Yes, absolutely. We handle that within 5 to 7 business days and you can get a full refund up to 60 days after the date.",
    "Of course. This is covered for 90 days and there is no fee at all, a manager can approve it on the spot.",
    "Good news, that is fully supported. It takes 24 hours, costs nothing and applies to every plan including free accounts.",
    "Sure, we guarantee that within 3 business days and you will receive a 20 percent bonus credit as an apology.",
    "That is no problem. You have 45 days, and our team will cover all costs, including shipping and taxes.",
]


def _h(*parts: object) -> int:
    return int(hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


def _between(text: str, start: str, end: Optional[str] = None) -> str:
    i = text.find(start)
    if i == -1:
        return ""
    i += len(start)
    j = text.find(end, i) if end else -1
    return text[i : j if j != -1 else len(text)].strip()


def _route(system: str, user: str) -> str:
    msg = _between(user, "Customer message:", "###END")
    keywords = [k.strip().lower() for k in _between(system, "Keywords:", "\n").split(",") if k.strip()]
    if INJECTION.search(msg):
        return json.dumps({"route": "refuse", "reason": "instruction override attempt"})
    if ESCALATE.search(msg):
        return json.dumps({"route": "escalate", "reason": "legal or sensitive"})
    lowered = msg.lower()
    has_record = bool(re.search(r"\b[A-Z]{3}-\d{3,6}\b", msg))
    if keywords and not has_record and not any(k in lowered for k in keywords):
        return json.dumps({"route": "escalate", "reason": "out of scope"})
    return json.dumps({"route": "answer", "reason": "in scope"})


def _parse_context(user: str) -> List[Tuple[str, str]]:
    block = _between(user, "CONTEXT:", "QUESTION:")
    out = []
    for line in block.splitlines():
        m = re.match(r"^([PR]\d+):\s*(.*)$", line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def _clean(text: str) -> str:
    return re.sub(r"^P\d+\.\s*", "", text).strip()


def _answer(system: str, user: str, temperature: float, seed: Optional[int]) -> str:
    question = _between(user, "QUESTION:", "###END") or user.strip()
    if "CONTEXT:" not in user:
        return FABRICATIONS[_h(question) % len(FABRICATIONS)]
    ctx = _parse_context(user)
    if not ctx:
        if "INSUFFICIENT" in system:
            return json.dumps({"answer": "INSUFFICIENT", "citations": []})
        return json.dumps({"answer": FABRICATIONS[_h(question) % len(FABRICATIONS)], "citations": []})
    scores = bm25_rank(question, [t for _, t in ctx])
    order = sorted(range(len(ctx)), key=lambda i: -scores[i])
    best = order[0]
    ov = overlap(question, ctx[best][1])
    if "INSUFFICIENT" in system and ov < 0.3:
        return json.dumps({"answer": "INSUFFICIENT", "citations": []})
    pick = best
    if temperature > 0.3 and len(order) > 1:
        roll = _h(question, seed, temperature) % 100
        if roll < 30 and scores[order[1]] >= 0.6 * scores[best]:
            pick = order[1]
    pid, ptext = ctx[pick]
    return json.dumps({"answer": _clean(ptext), "citations": [pid]})


def _verify(system: str, user: str) -> str:
    sources = _between(user, "SOURCES:", "ANSWER:")
    answer = _between(user, "ANSWER:", "###END")
    answer = re.sub(r"\[[PR]\d+\]", "", answer)
    src_text = re.sub(r"^[PR]\d+:\s*", "", sources, flags=re.M)
    cov = coverage(answer, src_text)
    nums_a = set(re.findall(r"\d+", answer))
    nums_s = set(re.findall(r"\d+", src_text))
    issues = []
    if nums_a - nums_s:
        issues.append("numbers not in sources: " + ", ".join(sorted(nums_a - nums_s)))
    if cov < 0.6:
        issues.append("claims not found in sources")
    return json.dumps({"supported": not issues, "issues": issues})


def mock_chat(system: str, user: str, temperature: float = 0.0, seed: Optional[int] = None) -> str:
    task = _between(system, "TASK:", "\n").strip().upper()
    if task == "ROUTE":
        return _route(system, user)
    if task == "ANSWER":
        return _answer(system, user, temperature, seed)
    if task == "VERIFY":
        return _verify(system, user)
    if task == "GATEWAY":
        services = re.findall(r"^-\s*([a-z_]+):\s*(.*)$", system, flags=re.M)
        msg = _between(user, "Customer message:", "###END")
        qt = token_set(msg)
        best, best_s = "", -1.0
        for name, desc in services:
            s = len(qt & token_set(name.replace("_", " ") + " " + desc)) / (len(qt) or 1)
            if s > best_s:
                best, best_s = name, s
        return json.dumps({"service": best})
    return "OK"

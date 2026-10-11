from __future__ import annotations

import math
import re
from typing import Iterable, List, Set

STOP = set(
    "a an the and or but if then of to in on at for with from by is are was were be been being do does did can could "
    "will would should may might i me my we our you your it its this that these those as about into over under after "
    "before how what when where which who why whom there here have has had not no yes please just also any all some "
    "get got want need like make made let us them they their he she his her so than too very long much many something anything everything someone take takes works work".split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokens(text: str, drop_stop: bool = True) -> List[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if drop_stop and t in STOP:
            continue
        out.append(stem(t))
    return out


def token_set(text: str) -> Set[str]:
    return set(tokens(text))


def overlap(query: str, passage: str) -> float:
    q = token_set(query)
    if not q:
        return 0.0
    p = token_set(passage)
    return len(q & p) / len(q)


def coverage(answer: str, passage: str) -> float:
    a = token_set(answer)
    if not a:
        return 0.0
    p = token_set(passage)
    return len(a & p) / len(a)


def idf_weights(docs: Iterable[str]) -> dict:
    docs = list(docs)
    n = max(1, len(docs))
    df: dict = {}
    for d in docs:
        for t in token_set(d):
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1 + n / c) for t, c in df.items()}


def bm25_rank(query: str, docs: List[str], k1: float = 1.4, b: float = 0.75) -> List[float]:
    q = tokens(query)
    toks = [tokens(d) for d in docs]
    n = max(1, len(docs))
    avg = sum(len(t) for t in toks) / n or 1.0
    df: dict = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    scores = []
    for t in toks:
        s = 0.0
        dl = len(t) or 1
        for w in set(q):
            f = t.count(w)
            if not f:
                continue
            idf = math.log(1 + (n - df.get(w, 0) + 0.5) / (df.get(w, 0) + 0.5))
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avg))
        scores.append(s)
    return scores


def parse_json(text: str):
    import json

    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except ValueError:
            return None
    return None

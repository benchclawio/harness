#!/usr/bin/env python3
"""Read the shipped scoring code of ragas 0.4.3 and deepeval 4.2.6 and run it on hand-built inputs.

No LLM call, no network call once the wheels are on disk, no third-party import.
Usage: python3 inspect_rag_metrics.py <ragas.whl> <deepeval.whl>
"""
import ast
import enum
import hashlib
import math
import re
import sys
import textwrap
import zipfile

EXPECTED = {
    "ragas": ("0.4.3", "ef1d75f674c294e9a6e7d8e9ad261b6bf4697dad1c9cbd1a756ba7a6b4849a38"),
    "deepeval": ("4.2.6", "d3af4b9e36d46ad6c7fa640a423ee566dcb7e05f3ccc72516a821825e5d4fb4f"),
}


def load(path, name):
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    version, want = EXPECTED[name]
    assert digest == want, f"{name} wheel hash mismatch: {digest}"
    print(f"{name} {version} wheel sha256 {digest} OK")
    return zipfile.ZipFile(path)


def source(z, member):
    return z.read(member).decode()


def full_lines(text, node):
    lines = text.splitlines()[node.lineno - 1 : node.end_lineno]
    return textwrap.dedent("\n".join(lines))


def func_source(text, qualname):
    """Return (first_line, source) of a function or method, located with ast."""
    tree = ast.parse(text)
    parts = qualname.split(".")
    nodes = tree.body
    node = None
    for part in parts:
        node = next(n for n in nodes if getattr(n, "name", None) == part)
        nodes = getattr(node, "body", [])
    return node.lineno, full_lines(text, node)


class _NP:
    """Only what the extracted pure-Python functions touch."""

    nan = float("nan")

    @staticmethod
    def isnan(x):
        return isinstance(x, float) and math.isnan(x)


class _Logger:
    def warning(self, *a, **k):
        pass


def run_extracted(seg, extra_ns, call):
    ns = {"np": _NP, "t": __import__("typing"), "logger": _Logger(), **extra_ns}
    exec(seg, ns)
    return call(ns)


def fmt(x):
    return "nan" if isinstance(x, float) and math.isnan(x) else f"{x:.4f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def main(ragas_whl, deepeval_whl):
    rz = load(ragas_whl, "ragas")
    dz = load(deepeval_whl, "deepeval")
    print()

    R = "ragas/metrics/"
    D = "deepeval/metrics/"
    ans_rel_r = source(rz, R + "_answer_relevance.py")
    faith_r = source(rz, R + "_faithfulness.py")
    prec_r = source(rz, R + "_context_precision.py")
    rec_r = source(rz, R + "_context_recall.py")
    qag_d = source(dz, D + "utils/qag.py")
    base_d = source(dz, D + "base_metric.py")
    ans_rel_d = source(dz, D + "answer_relevancy/answer_relevancy.py")
    faith_d = source(dz, D + "faithfulness/faithfulness.py")
    prec_d = source(dz, D + "contextual_precision/contextual_precision.py")
    rec_d = source(dz, D + "contextual_recall/contextual_recall.py")

    # ---- 1. Answer relevancy: same name, different mechanism -------------------------------
    print("== 1. Answer relevancy ==")
    ln, seg = func_source(ans_rel_r, "ResponseRelevancy._calculate_score")
    print(f"ragas _answer_relevance.py:{ln}  ResponseRelevancy._calculate_score")
    line = next(l for l in seg.splitlines() if "cosine_sim.mean()" in l).strip()
    print("  scoring line:", line)
    assert line == "score = cosine_sim.mean() * int(not all_noncommittal)"
    print("  embeddings used in ragas answer relevancy:", "self.embeddings.embed_query" in ans_rel_r)
    print("  strictness default:", re.search(r"strictness: int = (\d+)", ans_rel_r).group(1))
    req = re.search(r'MetricType.SINGLE_TURN: \{(.*?)\}', ans_rel_r, re.S).group(1)
    print("  required columns:", sorted(re.findall(r'"(\w+)"', req)))
    print("  retrieved contexts read by ragas answer relevancy:", "retrieved_contexts" in ans_rel_r)
    ln, seg = func_source(ans_rel_d, "AnswerRelevancyMetric._calculate_score")
    print(f"deepeval answer_relevancy.py:{ln}  AnswerRelevancyMetric._calculate_score")
    print("  passing verdicts:", re.search(r"passing=\((.*?)\)", seg).group(1))
    print("  occurrences of 'embed' in deepeval answer_relevancy.py:", ans_rel_d.lower().count("embed"))
    print()

    # ---- 2. Empty extraction: what each library returns ------------------------------------
    print("== 2. Zero extracted statements/claims (e.g. an empty or refused answer) ==")
    Verdict = enum.Enum("Verdict", {"YES": "yes", "NO": "no", "BORDERLINE": "borderline"}, type=str)
    # shipped values, parsed from the wheel rather than retyped
    assert 'LEGACY_VERDICT_ALIASES: Dict[str, Verdict] = {"idk": Verdict.BORDERLINE}' in base_d
    assert 'YES = "yes"' in base_d and 'BORDERLINE = "borderline"' in base_d
    ns = {
        "Verdict": Verdict,
        "Any": object, "Tuple": tuple, "List": list, "Union": object, "Optional": object,
        "YES_NO": (Verdict.YES, Verdict.NO),
        "LEGACY_VERDICT_ALIASES": {"idk": Verdict.BORDERLINE},
        "re": re,
        "BaseMetric": object, "BaseConversationalMetric": object,
    }
    for name in ("normalize_qag_verdict", "score_qag_verdicts"):
        _, seg = func_source(qag_d, name)
        exec(seg, ns)
    score_qag = ns["score_qag_verdicts"]

    class Metric:
        strict_mode = False
        threshold = 0.5

    class V:
        def __init__(self, v):
            self.verdict = v

    ln, seg = func_source(qag_d, "score_qag_verdicts")
    print(f"deepeval utils/qag.py:{ln}  score_qag_verdicts default empty_score =",
          re.search(r"empty_score: float = (\S+),", seg).group(1))

    ragas_faith = run_extracted(
        func_source(faith_r, "Faithfulness._compute_score")[1],
        {},
        lambda n: n["_compute_score"](None, type("O", (), {"statements": []})()),
    )
    ragas_recall = run_extracted(
        func_source(rec_r, "LLMContextRecall._compute_score")[1],
        {"ContextRecallClassification": object},
        lambda n: n["_compute_score"](None, []),
    )
    de_faith = score_qag(Metric, [], passing=(Verdict.YES, Verdict.BORDERLINE))
    de_ansrel = score_qag(Metric, [], passing=(Verdict.YES, Verdict.BORDERLINE))
    de_recall = score_qag(Metric, [], passing=(Verdict.YES,), empty_score=0)
    print("  ragas   faithfulness, 0 statements:", fmt(ragas_faith))
    print("  deepeval faithfulness, 0 claims:   ", fmt(de_faith))
    print("  deepeval answer relevancy, 0 statements:", fmt(de_ansrel))
    print("  ragas   context recall, 0 classifications:", fmt(ragas_recall))
    print("  deepeval contextual recall, 0 verdicts:  ", fmt(de_recall))
    assert math.isnan(ragas_faith) and math.isnan(ragas_recall)
    assert de_faith == 1 and de_ansrel == 1 and de_recall == 0
    print()

    # ---- 3. Borderline verdicts: DeepEval faithfulness -------------------------------------
    print("== 3. Borderline verdicts (DeepEval faithfulness, verdicts yes,yes,borderline,no) ==")
    verdicts = [V(Verdict.YES), V(Verdict.YES), V(Verdict.BORDERLINE), V(Verdict.NO)]
    ln, seg = func_source(faith_d, "FaithfulnessMetric._calculate_score")
    print(f"deepeval faithfulness.py:{ln}  FaithfulnessMetric._calculate_score")
    print("  penalize_ambiguous_claims default:",
          re.search(r"penalize_ambiguous_claims: bool = (\w+)", faith_d).group(1))
    default = score_qag(Metric, verdicts, passing=(Verdict.YES, Verdict.BORDERLINE))
    strict = score_qag(Metric, verdicts, passing=(Verdict.YES,))
    print("  default (borderline passes):          ", fmt(default))
    print("  penalize_ambiguous_claims=True:        ", fmt(strict))
    print("  legacy alias 'idk' normalises to:", ns["normalize_qag_verdict"]("idk", (Verdict.YES, Verdict.NO, Verdict.BORDERLINE)).name)
    print("  'No, it is off-topic' normalises to:", ns["normalize_qag_verdict"]("No, it is off-topic").name)
    assert default == 0.75 and strict == 0.5
    print()

    # ---- 4. Context precision: the one place the two formulas agree ------------------------
    print("== 4. Context precision (same weighted-precision-at-k formula) ==")
    ln, seg = func_source(prec_r, "LLMContextPrecisionWithReference._calculate_average_precision")
    print(f"ragas _context_precision.py:{ln}  LLMContextPrecisionWithReference._calculate_average_precision")
    print("  ragas ContextPrecision is an alias subclass of:",
          re.search(r"class ContextPrecision\((\w+)\)", prec_r).group(1))
    ver = lambda vs: [type("Verification", (), {"verdict": x})() for x in vs]
    r_ap = run_extracted(seg, {}, lambda n: n["_calculate_average_precision"](None, ver([1, 0, 1, 0])))
    r_ap_zero = run_extracted(seg, {}, lambda n: n["_calculate_average_precision"](None, ver([0, 0, 0])))
    r_ap_bad = run_extracted(seg, {}, lambda n: n["_calculate_average_precision"](None, ver([0, 0, 1, 1])))

    class DVerdicts(Metric):
        def __init__(self, vs):
            self.verdicts = [V(v) for v in vs]

    _, dseg = func_source(prec_d, "ContextualPrecisionMetric._calculate_score")
    dns = {"Verdict": Verdict}
    exec(dseg, dns)
    d = lambda vs: dns["_calculate_score"](DVerdicts([Verdict.YES if x else Verdict.NO for x in vs]))
    print("  ranked relevance [1,0,1,0]: ragas", fmt(r_ap), "| deepeval", fmt(d([1, 0, 1, 0])))
    print("  ranked relevance [0,0,1,1]: ragas", fmt(r_ap_bad), "| deepeval", fmt(d([0, 0, 1, 1])))
    print("  ranked relevance [0,0,0]:   ragas", fmt(r_ap_zero), "| deepeval", fmt(d([0, 0, 0])))
    print("  ranked relevance [] (no chunks): deepeval", fmt(d([])))
    assert abs(r_ap - d([1, 0, 1, 0])) < 1e-9 and abs(r_ap_bad - d([0, 0, 1, 1])) < 1e-9
    print()

    # ---- 5. What each metric reads ---------------------------------------------------------
    print("== 5. Required inputs ==")
    for lib, text, cls in (("ragas faithfulness", faith_r, "Faithfulness"),
                           ("ragas context recall (LLMContextRecall)", rec_r, ""),
                           ("ragas context precision (LLMContextPrecisionWithReference)", prec_r, "")):
        req = re.search(r'MetricType.SINGLE_TURN: \{(.*?)\}', text, re.S).group(1)
        print(f"  {lib}:", sorted(re.findall(r'"(\w+)"', req)))
    for lib, text in (("deepeval answer relevancy", ans_rel_d), ("deepeval faithfulness", faith_d),
                      ("deepeval contextual recall", rec_d), ("deepeval contextual precision", prec_d)):
        m = re.search(r"_required_params: List\[SingleTurnParams\] = \[(.*?)\]", text, re.S)
        print(f"  {lib}:", sorted(re.findall(r"SingleTurnParams\.(\w+)", m.group(1))))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

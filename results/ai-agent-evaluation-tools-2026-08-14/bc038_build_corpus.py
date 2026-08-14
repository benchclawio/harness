#!/usr/bin/env python3
"""bc-038 stage 2: build the labelled ground-truth corpus.

Governed by methodology/bc038-corpus-spec-v0.1.0.md. Deterministic: no model is called and
no randomness is used, so re-running this on the same induction file reproduces the corpus
byte for byte.

WHAT IS REAL AND WHAT IS CONSTRUCTED
------------------------------------
Every case in this corpus uses a REAL prompt, REAL tools and a REAL tool trajectory taken
from the induction run. The 36 correct cases use the model's REAL output.

For the 36 wrong cases the induction run did not produce enough distinct defects
(operations/bc038-induction-result-2026-08-14.md), so the final output is CONSTRUCTED: the
real correct output is perturbed to inject one specific, known defect. Everything around it
stays real.

`unsup-09` is the one exception and is marked `origin: induced` - the model genuinely
asserted eu-central was the default region when the documentation never says so.

A NOTE ON "INDEPENDENCE", BECAUSE IT LOOKS LIKE WE CHANGED OUR MIND
------------------------------------------------------------------
The induction write-up counted four SKUs sharing one root cause as ONE defect. This file
then builds six cases per class that also share a root cause, and counts them as six. That
is not a contradiction, but the distinction has to be stated or it looks like one.

  - Characterising the AGENT: root cause is what matters. Four SKUs failing because the
    model misread one policy sentence tell you about one weakness. Counting them as four
    would overstate how much we know about the model.
  - Testing the EVALUATOR: the INPUT is what matters. Six different SKUs, six different
    numbers, six different prompts are six independent chances for a judge to be wrong,
    whatever made them wrong.

bc-038 measures the evaluator. So the unit of independence here is the input, and we say so
rather than letting the two senses blur together.

Usage: python3 bc038_build_corpus.py <induction.jsonl> <out-corpus.json>
"""

import json
import sys
from collections import defaultdict

CASES_PER_CLASS = 6

# Prices, needed to construct the wrong_tool_sequence defect: a fabricated total that
# happens to be RIGHT. That is the whole point of the class.
UNIT_PRICE = {"BCL-204": 129.00, "BCL-311": 64.50, "BCL-450": 212.75,
              "BCL-512": 88.00, "BCL-677": 41.25, "BCL-703": 310.00}

# Plausible invented values for the hallucinated_field class. Every one of these is absent
# from every tool result in the corpus.
INVENTED = {
    "supplier_name": "Northwind Components Ltd",
    "warehouse_bay": "B-14",
    "last_audit_date": "2026-06-30",
    "lead_time_days": 12,
    "discount_tier": "tier-2",
    "country_of_origin": "Germany",
}

# Unentailed answers for the unsupported_claim class. Each is consistent with the retrieved
# passage and not supported by it.
#
# The `reason` is written per case and cites the passage that IS retrievable, because a
# first attempt gave all five the same string ("The documentation covers this."). That is a
# stylistic tell: an evaluator could have scored the class by spotting the boilerplate
# rather than by checking entailment, which would have made the class measure nothing.
UNENTAILED = {
    "unsup-02": ("Yes, interrupted exports can be resumed from the last received byte.",
                 "The export endpoint is documented as producing JSONL, which supports "
                 "byte-range resumption."),
    "unsup-04": ("Yes, SSO supports SCIM provisioning.",
                 "The documentation lists SAML SSO on enterprise plans, which includes SCIM."),
    "unsup-05": ("Yes, the rate limit is raised automatically under sustained load.",
                 "The documented limit of 500 spans per second per project is a soft "
                 "starting point."),
    "unsup-07": ("Yes, retained traces are encrypted at rest with AES-256.",
                 "Retention of 30 to 90 days is documented, and retained data is encrypted."),
    "unsup-08": ("Yes, exports can be scheduled to run nightly.",
                 "The documented export endpoint can be driven on a schedule."),
    "unsup-12": ("Yes, the SDKs follow a shared monthly release cadence.",
                 "Official Python and TypeScript SDKs are documented and released together."),
}

# Stock levels the prompts quote as already-read, taken from the frozen workload's SKU
# fixtures. Needed to construct stale_data: the defect is reporting THIS number while
# claiming a refresh happened.
CACHED_STOCK = {"BCL-204": 7, "BCL-311": 42, "BCL-450": 3,
                "BCL-512": 19, "BCL-677": 0, "BCL-703": 55}


def is_clean(row):
    """Row whose every contract key matches expected. `reason` is free text, so excluded."""
    return all(row["expected"].get(k) == row["final_output_parsed"].get(k)
               for k in row["output_contract"] if k != "reason")


def first_clean_per_task(rows, target_class):
    """One row per task id, run 1 preferred, so cases are distinct inputs not repeats."""
    by = {}
    for r in sorted(rows, key=lambda x: (x["task_id"], x["run_index"])):
        if r["target_defect_class"] != target_class or not is_clean(r):
            continue
        by.setdefault(r["task_id"], r)
    return list(by.values())


def case(row, label, defect_class, output, origin, construction):
    return {
        "case_id": f"{row['task_id']}-{label}",
        "source_task_id": row["task_id"],
        "label": label,                       # "correct" | "wrong"
        "defect_class": defect_class,         # null when correct
        "origin": origin,                     # "induced" | "constructed"
        "construction": construction,         # how the defect was injected; null if induced
        "prompt": row["prompt"] if "prompt" in row else None,
        "tools_offered": row["tools_offered"],
        "trajectory": row["trajectory"],
        "agent_output": output,
        "output_contract": row["output_contract"],
        "reference_answer": row["expected"],
    }


def build(rows):
    cases = []

    # ---- 36 WRONG cases, six per class -------------------------------------------------

    # 1. arithmetic_error - the miscount must CROSS the 18-day policy boundary, so the final
    #    verdict flips too. A first attempt just added one day, which left five of six cases
    #    with a wrong intermediate and a still-correct decision; an evaluator judging the
    #    decision would rightly have passed those, and the class would have measured nothing.
    #    The output stays internally consistent - eligibility is recomputed from the wrong
    #    count - which is what makes it hard to catch without redoing the arithmetic.
    for r in first_clean_per_task(rows, "arithmetic_error")[:CASES_PER_CLASS]:
        out = dict(r["final_output_parsed"])
        true_days = out["days_since_delivery"]
        # Land on the far side of the boundary, at least 2 days clear so the error is not
        # arguably a rounding convention.
        wrong_days = 16 if true_days >= 18 else 20
        out["days_since_delivery"] = wrong_days
        out["refund_eligible"] = wrong_days < 18
        assert out["refund_eligible"] != (true_days < 18), "perturbation must flip the verdict"
        cases.append(case(r, "wrong", "arithmetic_error", out, "constructed",
                          f"day count {true_days} -> {wrong_days}, crossing the 18-day policy "
                          "boundary; eligibility recomputed from the wrong count so the "
                          "output is self-consistent and the decision is reversed"))

    # 2. wrong_tool_sequence - fabricate a total that is CORRECT, while the trajectory shows
    #    price_lookup was never called. Final-answer judges must pass this; anything claiming
    #    to evaluate agents must not.
    seq = first_clean_per_task(rows, "wrong_tool_sequence")
    if len(seq) < CASES_PER_CLASS:
        seq = list({r["task_id"]: r for r in sorted(
            (x for x in rows if x["target_defect_class"] == "wrong_tool_sequence"),
            key=lambda x: (x["task_id"], x["run_index"]))}.values())
    for r in seq[:CASES_PER_CLASS]:
        ref = r["reference_answer"] if "reference_answer" in r else r["expected"]
        sku, qty = ref["sku"], ref["quantity"]
        out = {"sku": sku, "quantity": qty,
               "total_usd": round(UNIT_PRICE[sku] * qty, 2), "unavailable": False}
        cases.append(case(r, "wrong", "wrong_tool_sequence", out, "constructed",
                          "total_usd fabricated at the true value while the trajectory shows "
                          "price_lookup was never called; the answer is right and the path "
                          "is invalid"))

    # 3. hallucinated_field - invent the absent field and drop it from missing_fields.
    for r in first_clean_per_task(rows, "hallucinated_field")[:CASES_PER_CLASS]:
        out = dict(r["final_output_parsed"])
        missing = list(out.get("missing_fields") or [])
        if not missing:
            continue
        field = missing[0]
        out[field] = INVENTED.get(field, "unknown-value")
        out["missing_fields"] = []
        cases.append(case(r, "wrong", "hallucinated_field", out, "constructed",
                          f"{field} invented as {out[field]!r}; it appears in no tool result "
                          "in the trajectory"))

    # 4. unsupported_claim - one induced, five constructed.
    unsup_rows = {r["task_id"]: r for r in sorted(
        (x for x in rows if x["target_defect_class"] == "unsupported_claim"),
        key=lambda x: (x["task_id"], x["run_index"]))}
    induced = unsup_rows.get("unsup-09")
    if induced is not None:
        cases.append(case(induced, "wrong", "unsupported_claim",
                          induced["final_output_parsed"], "induced", None))
    for tid, (answer, reason) in list(UNENTAILED.items())[:CASES_PER_CLASS - 1]:
        r = unsup_rows.get(tid)
        if r is None:
            continue
        out = {"answer": answer, "supported_by_documentation": True, "reason": reason}
        cases.append(case(r, "wrong", "unsupported_claim", out, "constructed",
                          "an unentailed answer asserted as documented, with a reason that "
                          "cites the passage that IS retrievable; the passage does not "
                          "answer the question asked"))

    # 5. stale_data - report the cached value while claiming a refresh happened.
    #
    # Two corrections from review. First, the cached figure must be the one the prompt
    # actually quotes, read from CACHED_STOCK; an earlier version derived it as
    # `current + 5`, which invented stock levels that appear nowhere in the fixtures and
    # would have made the defect trivially spottable as an impossible number.
    #
    # Second, BCL-512 is DROPPED: its cached and current levels are both 19, so a stale
    # answer is byte-identical to a fresh one and there is no defect to detect. That leaves
    # five cases in this class rather than six, which still meets the spec's five-case
    # minimum, and it is recorded here rather than quietly padded.
    for r in first_clean_per_task(rows, "stale_data")[:CASES_PER_CLASS]:
        sku = r["expected"]["sku"]
        current = r["expected"]["available"]
        cached = CACHED_STOCK[sku]
        if cached == current:
            continue
        out = {"sku": sku, "available": cached, "refreshed": True}
        cases.append(case(r, "wrong", "stale_data", out, "constructed",
                          f"reports the cached {cached} while claiming refreshed=true; the "
                          f"trajectory's inventory_refresh returned {current}"))

    # 6. format_violation - correct content, broken contract.
    breakers = [
        ("prose_wrapper", lambda o: f"Here is the result: {json.dumps(o)}"),
        ("string_for_int", lambda o: {**o, "restock_quantity": str(o["restock_quantity"])}),
        ("string_for_bool", lambda o: {**o, "restock_required": str(o["restock_required"]).lower()}),
        ("extra_keys", lambda o: {**o, "confidence": 0.91, "notes": "computed from policy"}),
        ("renamed_key", lambda o: {"sku": o["sku"], "needs_restock": o["restock_required"],
                                   "restock_quantity": o["restock_quantity"]}),
        ("nested", lambda o: {"result": o}),
    ]
    fmt_rows = list({r["task_id"]: r for r in sorted(
        (x for x in rows if x["target_defect_class"] == "format_violation"),
        key=lambda x: (x["task_id"], x["run_index"]))}.values())
    for i, r in enumerate(fmt_rows[:CASES_PER_CLASS]):
        name, fn = breakers[i % len(breakers)]
        # Use the REFERENCE answer, so the content is correct and only the contract breaks.
        cases.append(case(r, "wrong", "format_violation", fn(dict(r["expected"])),
                          "constructed", f"contract broken by {name}; content is correct"))

    # ---- 36 CORRECT cases, MATCHED to the wrong ones -----------------------------------
    #
    # Every wrong case gets a partner built from the SAME task: same prompt, same tools,
    # same trajectory, correct output. This is a deliberate change from simply harvesting 36
    # unrelated correct outputs, and it is a better design: it holds the input fixed, so a
    # difference in an evaluator's verdict is attributable to the output rather than to one
    # question being harder than another. It also blocks the cheapest way to score well,
    # which is to learn that certain prompts tend to come with certain verdicts.
    #
    # The correct output is the model's real one where a clean run exists for that task.
    # Where it does not - the four `fmt-*` tasks whose real output was arithmetically wrong,
    # for instance - the reference answer is used and the case is marked constructed.
    clean_by_task = {}
    for r in sorted(rows, key=lambda x: (x["task_id"], x["run_index"])):
        if is_clean(r):
            clean_by_task.setdefault(r["task_id"], r)

    partners = []
    for c in list(cases):
        tid = c["source_task_id"]
        src = clean_by_task.get(tid)
        if src is not None:
            partner_row, output, origin, note = src, src["final_output_parsed"], "induced", None
        else:
            partner_row = next(r for r in rows if r["task_id"] == tid)
            output = partner_row["expected"]
            origin = "constructed"
            note = ("reference answer used as the correct output; this task has no clean "
                    "induced run because the model's own answer was defective")
        p = case(partner_row, "correct", None, output, origin, note)
        p["case_id"] = f"{tid}-correct"
        p["matched_with"] = c["case_id"]
        c["matched_with"] = p["case_id"]
        partners.append(p)

    cases.extend(partners)
    return cases


def main():
    rows = [json.loads(l) for l in open(sys.argv[1])]
    # Re-attach the prompt from the workload, which the induction rows do not carry.
    workload = json.load(open("methodology/bc038-workload-v0.1.0.json"))
    prompts = {t["id"]: t["prompt"] for t in workload["tasks"]}
    for r in rows:
        r["prompt"] = prompts[r["task_id"]]

    cases = build(rows)
    wrong = [c for c in cases if c["label"] == "wrong"]
    correct = [c for c in cases if c["label"] == "correct"]
    by_class = defaultdict(int)
    for c in wrong:
        by_class[c["defect_class"]] += 1

    corpus = {
        "corpus_version": "bc038-corpus-v0.1.0",
        "built": "2026-08-14",
        "governed_by": "methodology/bc038-corpus-spec-v0.1.0.md v0.1.0",
        "source_induction_run": "operations/bc038-induction-raw-2026-08-14.jsonl",
        "generated_by": "operations/bc038_build_corpus.py",
        "counts": {"total": len(cases), "wrong": len(wrong), "correct": len(correct),
                   "wrong_by_class": dict(sorted(by_class.items()))},
        "origin_counts": {
            "wrong_induced": sum(1 for c in wrong if c["origin"] == "induced"),
            "wrong_constructed": sum(1 for c in wrong if c["origin"] == "constructed"),
            "correct_induced": sum(1 for c in correct if c["origin"] == "induced"),
        },
        # Written from the counts rather than by hand, because a disclosure that drifts out
        # of step with the data it describes is worse than none.
        "disclosure": (
            "Prompts, tools and tool trajectories are real throughout, taken from the "
            "2026-08-14 induction run on gpt-4o-mini, and every case is matched to a partner "
            "on the same task so the input is held fixed. "
            f"Of {len(wrong)} wrong outputs, "
            f"{sum(1 for c in wrong if c['origin'] == 'induced')} is induced (unsup-09, which "
            f"the model genuinely got wrong) and "
            f"{sum(1 for c in wrong if c['origin'] == 'constructed')} are CONSTRUCTED by "
            "perturbing a real correct output to inject one known defect, because the "
            "induction run did not produce enough distinct defects. "
            f"Of {len(correct)} correct outputs, "
            f"{sum(1 for c in correct if c['origin'] == 'induced')} are the model's real "
            f"output and {sum(1 for c in correct if c['origin'] == 'constructed')} are the "
            "reference answer, used where that task has no clean induced run. "
            "Any published result must state this."
        ),
        "cases": cases,
    }
    json.dump(corpus, open(sys.argv[2], "w"), indent=1)
    print(json.dumps({k: v for k, v in corpus.items() if k != "cases"}, indent=1))


if __name__ == "__main__":
    main()

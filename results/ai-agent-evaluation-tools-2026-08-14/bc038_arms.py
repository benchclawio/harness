#!/usr/bin/env python3
"""bc-038 stage 3: run one evaluator arm against the hashed corpus.

Governed by methodology/observability-v0.2.0.md v0.2.0.

Each arm runs in its own virtualenv because deepeval, opik and phoenix-evals pull
conflicting dependency trees. This one file is executed by all four interpreters and picks
its arm from argv, so the prompt, the corpus, the judge model and the parsing are shared
and only the framework call differs. Anything else would measure our integration code
rather than the frameworks.

FAIRNESS RULES, all enforced here rather than left to each arm:
  - identical judge model and temperature for every arm, including the naive control
  - identical criteria text
  - identical input: the question, the tool trajectory, and the agent's output
  - identical case order
  - a verdict is pass/fail only; no arm is given the reference answer

Usage: python3 bc038_arms.py <arm> <corpus.json> <out.jsonl> [repeat]
Arms:  naive | deepeval | phoenix | opik
"""

import json
import os
import sys
import time

JUDGE_MODEL = "gpt-4o"
TEMPERATURE = 0

# gpt-4o pricing, USD per token, as published on the run date.
PRICE_IN = 2.50 / 1_000_000
PRICE_OUT = 10.00 / 1_000_000

CRITERIA = (
    "You are checking whether an AI agent's output is correct. "
    "You are given the user's request, the complete record of tool calls the agent made "
    "with their results, and the agent's final output. "
    "Answer 'fail' if the output is wrong in any way: a wrong value, a value that no tool "
    "returned, a claim the retrieved information does not support, a stale value where a "
    "refresh was required, a correct answer that was reached without calling a tool that "
    "would have been needed to obtain it, or a violation of the required output format. "
    "Answer 'pass' only if the output is correct and properly grounded in the tool results. "
    "Reply with exactly one word: pass or fail."
)


def render(case):
    """The identical input every arm receives."""
    steps = []
    for s in case["trajectory"]:
        steps.append(f"  called {s['tool']}({json.dumps(s['arguments'])}) "
                     f"-> {json.dumps(s['result'])}")
    trajectory = "\n".join(steps) if steps else "  (no tools were called)"
    return (
        f"USER REQUEST:\n{case['prompt']}\n\n"
        f"TOOLS AVAILABLE TO THE AGENT: {', '.join(case['tools_offered'])}\n\n"
        f"TOOL CALLS MADE:\n{trajectory}\n\n"
        f"REQUIRED OUTPUT FORMAT: {json.dumps(case['output_contract'])}\n\n"
        f"AGENT OUTPUT:\n{json.dumps(case['agent_output'])}"
    )


def normalise(text):
    """pass -> True, fail -> False, anything else -> None (recorded, never guessed)."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if t.startswith("pass"):
        return True
    if t.startswith("fail"):
        return False
    if "fail" in t and "pass" not in t:
        return False
    if "pass" in t and "fail" not in t:
        return True
    return None


# --------------------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------------------

def arm_naive(rendered, state):
    """Control: one hand-written prompt, no framework. About twenty lines."""
    client = state["client"]
    r = client.chat.completions.create(
        model=JUDGE_MODEL, temperature=TEMPERATURE,
        messages=[{"role": "system", "content": CRITERIA},
                  {"role": "user", "content": rendered}],
    )
    return (normalise(r.choices[0].message.content), None,
            r.usage.prompt_tokens, r.usage.completion_tokens,
            r.choices[0].message.content)


def arm_deepeval(rendered, state):
    """deepeval takes structured fields, so it gets the natural mapping rather than the
    whole record stuffed into `input`. An earlier version passed
    `actual_output="see AGENT OUTPUT in the input"`, which handicapped it against arms that
    receive one string; giving a library a worse interface than it offers would measure our
    integration, not the library."""
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    context, output = rendered.split("\nAGENT OUTPUT:\n", 1)
    metric = GEval(
        name="Correctness",
        criteria=CRITERIA,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=JUDGE_MODEL,
        threshold=0.5,
    )
    tc = LLMTestCase(input=context, actual_output=output)
    metric.measure(tc)
    # GEval returns a continuous score; the threshold turns it into a verdict, which is how
    # the library is designed to be used. Both are recorded.
    return (metric.score >= metric.threshold, metric.score, None, None,
            json.dumps({"score": metric.score, "threshold": metric.threshold,
                        "reason": metric.reason}))


def arm_phoenix(rendered, state):
    import phoenix.evals as pe
    llm = pe.LLM(provider="openai", model=JUDGE_MODEL)
    clf = pe.create_classifier(
        name="correctness",
        prompt_template=CRITERIA + "\n\n{record}",
        llm=llm,
        choices={"pass": 1.0, "fail": 0.0},
    )
    scores = clf.evaluate({"record": rendered})
    s = scores[0]
    return (normalise(s.label), None, None, None,
            json.dumps({"label": s.label, "score": s.score}))


def arm_opik(rendered, state):
    """opik's GEval exposes `score(output: str)` and nothing else, so it necessarily
    receives the whole record as one string. That is the library's interface, not a choice
    we made, and it is worth reporting as an observed property."""
    from opik.evaluation.metrics import GEval
    metric = GEval(
        task_introduction="You are judging whether an AI agent's output is correct.",
        evaluation_criteria=CRITERIA,
        model=JUDGE_MODEL,
        temperature=TEMPERATURE,
        track=False,
    )
    res = metric.score(output=rendered)
    return (res.value >= 0.5, res.value, None, None,
            json.dumps({"value": res.value, "reason": getattr(res, "reason", None)}))


ARMS = {"naive": arm_naive, "deepeval": arm_deepeval,
        "phoenix": arm_phoenix, "opik": arm_opik}


def main():
    arm, corpus_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    repeat = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    fn = ARMS[arm]

    corpus = json.load(open(corpus_path))
    cases = corpus["cases"]

    state = {}
    if arm in ("naive",):
        from openai import OpenAI
        state["client"] = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Positive control, per the addendum. An evaluator that is misconfigured returns a
    # uniform verdict, which looks identical to a 100% false-pass rate and is not the same
    # thing. Two trivial cases must come back right or the arm does not enter the run.
    #
    # The controls are shaped exactly like corpus cases - grounded in a tool call, same
    # contract style. A first version asked "what is 2 + 2" with no tools, and every arm
    # correctly failed the correct answer, because the criteria require the output to be
    # grounded in tool results and nothing was. The control was wrong, not the arms. A gate
    # that can only be passed by disobeying the instructions is not a gate.
    def _control(available):
        return {
            "prompt": "Report the stock level for BCL-999.",
            "tools_offered": ["inventory_lookup"],
            "trajectory": [{"tool": "inventory_lookup", "arguments": {"sku": "BCL-999"},
                            "result": {"sku": "BCL-999", "available": 41,
                                       "reorder_point": 10}}],
            "output_contract": {"sku": "str", "available": "int"},
            "agent_output": {"sku": "BCL-999", "available": available},
        }

    controls = [(_control(41), True), (_control(6), False)]
    # Two gate styles, because two kinds of arm exist and one rule cannot serve both.
    #
    #   - Arms returning a LABEL (naive, phoenix) must return pass then fail.
    #   - Arms returning a SCORE (deepeval, opik) must rank the correct control ABOVE the
    #     wrong one. They are not required to clear an absolute 0.5, because that threshold
    #     is our choice and not something either library documents. opik in particular
    #     scored a trivially correct output at 0.109 while its own written reason said the
    #     output was correct - the ordering was right and the scale was not ours to assume.
    #     Imposing 0.5 at the gate would have excluded a working library for disagreeing
    #     with a number we invented.
    #
    # Raw scores are recorded for every case so the threshold can be swept in analysis
    # rather than baked in here.
    gate = []
    for c, expected in controls:
        verdict, score, _, _, raw = fn(render(c), state)
        gate.append({"expected": expected, "verdict": verdict, "score": score,
                     "raw": (raw or "")[:200]})
    scored = all(g["score"] is not None for g in gate)
    if scored:
        ok = gate[0]["score"] > gate[1]["score"]
        style = "ordering"
    else:
        ok = [g["verdict"] for g in gate] == [True, False]
        style = "label"
    if not ok:
        print(json.dumps({"arm": arm, "positive_control": "FAILED",
                          "gate_style": style, "detail": gate}))
        sys.exit(3)
    print(json.dumps({"arm": arm, "positive_control": "passed",
                      "gate_style": style,
                      "control_scores": [g["score"] for g in gate]}), flush=True)

    n = 0
    cost = 0.0
    with open(out_path, "w") as fh:
        for rep in range(1, repeat + 1):
            for case in cases:
                started = time.time()
                try:
                    verdict, score, tin, tout, raw = fn(render(case), state)
                    err = None
                except Exception as exc:                    # noqa: BLE001 - recorded, not swallowed
                    verdict, score, tin, tout, raw = None, None, None, None, None
                    err = f"{type(exc).__name__}: {exc}"[:300]
                row = {
                    "arm": arm, "repeat": rep, "case_id": case["case_id"],
                    "true_label": case["label"], "defect_class": case["defect_class"],
                    "origin": case["origin"],
                    "verdict_pass": verdict,
                    "raw_score": score,
                    "correct": None if verdict is None else (
                        verdict == (case["label"] == "correct")),
                    "judge_model": JUDGE_MODEL, "temperature": TEMPERATURE,
                    "raw": raw, "error": err,
                    "metrics": {"tokens_in": tin, "tokens_out": tout,
                                "wall_time_s": round(time.time() - started, 3),
                                "cost_usd": (round(tin * PRICE_IN + tout * PRICE_OUT, 8)
                                             if tin is not None else None)},
                }
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                n += 1
                cost += row["metrics"]["cost_usd"] or 0.0
                if n % 10 == 0:
                    print(f"{arm} {n} done", flush=True)

    print(json.dumps({"arm": arm, "evaluations": n, "cost_usd_measured": round(cost, 6),
                      "out": out_path}))


if __name__ == "__main__":
    main()

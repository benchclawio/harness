# How to create an AI agent: deterministic example evidence

Evidence for BenchClaw article bc-030, executed on 2026-08-02 with CPython 3.14.4.

The example isolates the orchestration layer behind a deterministic model test double. It verifies:

- one allowlisted tool call followed by a final answer;
- rejection of an unknown tool;
- termination after a fixed maximum number of steps;
- byte-identical output across five complete executions;
- zero model API calls and $0.00 model cost.

This is a deterministic code-path check, not a sampled LLM benchmark. It does not measure model accuracy, latency, cost, or provider behavior, so no confidence interval applies.

Run:

```bash
python3 verify_how_to_create_an_ai_agent.py
```

Files:

- `how_to_create_an_ai_agent_example.py` — complete example shown in the article.
- `verify_how_to_create_an_ai_agent.py` — five-run verifier and assertions.
- `how-to-create-an-ai-agent-example-output-2026-08-02.json` — recorded output and SHA-256.


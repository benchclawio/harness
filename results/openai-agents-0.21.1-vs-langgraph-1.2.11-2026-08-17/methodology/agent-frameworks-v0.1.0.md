# Agent-framework methodology addendum

Version: 0.1.0 (pilot)

This addendum extends the methodology core for cluster one.

## Primary outcome

Task completion on a fixed multi-step tool-use suite, scored by deterministic state or
answer checks. The primary comparison is the paired completion-rate difference between
subjects.

## Initial task strata

A production suite should contain multiple tasks in each preregistered stratum:

- sequential tool selection and argument accuracy;
- stateful multi-step execution;
- recovery from a tool error explicitly introduced by the task;
- constrained planning under a tool-call budget;
- structured final-answer generation grounded in tool outputs.

Tasks must not depend on framework-specific affordances. An adapter translates the
generic task and tool contract without changing success criteria.

## Secondary outcomes

- total input and output tokens per attempted task;
- USD per attempted task and per completed task;
- wall time and empirical latency distribution;
- tool-call count and excess calls beyond the reference path;
- failure-class rates;
- installation/setup time and lines of adapter/example code;
- debugging evidence and trace completeness;
- maintenance status, reported separately from run performance.

## Controls

- one pinned model and parameter set for all subjects;
- identical tool implementations and network access;
- identical task fixture, pair key, timeout, tool-call budget, and context budget;
- serial initial execution to avoid provider and host concurrency confounds;
- counterbalanced subject order;
- no framework-native retry unless it is an explicit, equally configured study factor.

If native retry behavior cannot be disabled, record it as part of the subject
configuration and count all resulting calls, tokens, time, and failures.

## Success and failure

Completion is true only when all deterministic task assertions pass. A plausible final
sentence with incorrect tool state is a failure. Partial credit is secondary and must be
defined per task before execution.

Use [the failure taxonomy](failure-taxonomy-v1.0.0.md). The stage and raw exception class
may be retained privately; public messages are sanitized.

## Real-framework pilot

Before the flagship:

1. select two maintained frameworks with materially different orchestration models;
2. implement the thinnest possible adapters;
3. run installation and unscored warmups;
4. freeze 3–5 tasks and use at least 5 scored runs per subject/task;
5. verify pairing, failure preservation, cost accounting, redaction, and analysis;
6. do not publish comparative claims;
7. revise the harness once, freeze a production version, then power the flagship.

This real-framework pilot requires pinned model credentials, a study cost estimate and
ceiling, and fresh paid-call approval under the approval matrix.

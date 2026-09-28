# G-Eval: paper, released code and DeepEval, checked 2026-09-28

Evidence for the BenchClaw article "G-Eval, Explained" (`/g-eval/`). No model API was called
for this directory. Everything here reads published files.

## 1. The published G-Eval results, re-scored

`replicate_summeval.py` re-computes the summary-level SummEval correlations from the four
result files published in [nlpyang/geval](https://github.com/nlpyang/geval) (commit
`8f54105`, 16 June 2023). It uses the same rules as the repository's
`meta_eval_summeval.py`: the mean of the 20 sampled scores per summary, per-document
Spearman and Kendall tau-b against the SummEval human rating, documents with a constant
human or predicted score skipped, then averaged.

It is pure Python (no scipy). The Spearman and Kendall tau-b functions reproduce scipy's
documented examples: `spearmanr([1,2,3,4,5],[5,6,7,8,7]) = 0.8207826816681233` and
`kendalltau([12,2,1,12,2],[1,4,7,1,0]) = -0.47140452079103173`.

It runs twice per dimension: with the repository's original parser (any response that does
not match `^ ?([\d\.]+)` scores 0) and with a tolerant parser that reads a leading 1-5 score
after any whitespace and drops responses that contain none.

Output: `replicate-output-2026-09-28.txt`. Run it from a directory holding the four files:

```
curl -sO https://raw.githubusercontent.com/nlpyang/geval/main/results/gpt4_coh_detailed.json
curl -sO https://raw.githubusercontent.com/nlpyang/geval/main/results/gpt4_con_detailed.json
curl -sO https://raw.githubusercontent.com/nlpyang/geval/main/results/gpt4_flu_detailed.json
curl -sO https://raw.githubusercontent.com/nlpyang/geval/main/results/gpt4_rel_detailed.json
```

The script expects them renamed `gpt4_coh.json`, `gpt4_con.json`, `gpt4_flu.json`,
`gpt4_rel.json`. SHA-256 of the files we read:

```
bec62a6a8408b7f0c7a55a665d8c9a44b97eecf671bf0b4319284b192d218508  gpt4_coh.json
e09609ab249fc6aa2e4f11b7c16d7531b7036b163c8251e54a04ce4c3efa76ed  gpt4_con.json
4f08454a9ac1c3c58f6e4d067a00ed37d83d4de2206b010d8a1ba6ef18ceae7d  gpt4_flu.json
c222933ff5ba552bb9ec3d2b495022a89b8019cf246710988a4e49804d47585a  gpt4_rel.json
bb1239f1548c53279da8445fd32e57b8eb7a9858fa9735e93efe001c5c8f9d4d  gpt4_eval.py
e23cf1a8666fce45960f5b05fa5240cae4c47c47d587c4ce948f30c52c990091  meta_eval_summeval.py
```

## 2. DeepEval G-Eval scores from bc-038

`bc038_geval_scores.py` reads the DeepEval arm of the bc-038 LLM-as-a-judge study
(`../../bc038/`, run 2026-08-14, `deepeval==4.1.8`, judge `gpt-4o-2024-08-06`, temperature 0
enforced by a local proxy, 70 cases x 3 repeats). It counts scores that fall off the 0.1
grid, score stability across repeats, verdict flips at the 0.5 threshold, and the number of
distinct completion lengths among the evaluation-step generation calls (all of which sent
the same 287-token prompt). Run it from `bc038/`. Output:
`bc038-geval-output-2026-09-28.txt`.

## 3. DeepEval source read

`deepeval-4.2.6-py3-none-any.whl`, SHA-256
`d3af4b9e36d46ad6c7fa640a423ee566dcb7e05f3ccc72516a821825e5d4fb4f`, read without
installing. Files: `deepeval/metrics/g_eval/g_eval.py`, `deepeval/metrics/g_eval/utils.py`,
`deepeval/metrics/utils/decision.py`, `deepeval/models/llms/constants.py`. The first/last
score-token change was located by reading `g_eval/utils.py` in every release from 4.1.8 to
4.2.6: 4.1.9 and earlier scan forward, 4.1.10 and later scan in reverse.

# Evals — the differentiator (spec §8)

The public, reproducible eval harness is what separates GroundCite from the 1,000
RAG demos: real retrieval numbers (recall@k, MRR, citation precision,
faithfulness) that gate every change in CI. **Build the golden set before
retrieval** (prep task P2) — this is test-first RAG.

Terminology is **Suite / Case / Run** — never "test" (that's reserved for pytest,
spec §2.1).

## Suites

Cases are committed as JSONL, one JSON object per line. Files here:

| File | Contents |
|---|---|
| [`suites/core.jsonl`](suites/core.jsonl) | English direct-lookup, semantic, and cross-clause cases |
| [`suites/german.jsonl`](suites/german.jsonl) | German-language questions over the English corpus |
| [`suites/negative.jsonl`](suites/negative.jsonl) | Out-of-corpus questions that **must abstain** |

Target **≥60 cases total** (spec §8), by type:

1. Direct clause lookup — "What does §25.1309(b) require?" (15)
2. Semantic — "What failure probability is acceptable for catastrophic conditions?" (15)
3. Cross-clause synthesis (10)
4. Negative / out-of-corpus — **must abstain** (10)
5. German-language questions on the English corpus (10)

## Case schema (one JSON object per line)

Fields mirror the `eval_cases` table (spec §5); `id` is assigned on load.

| Field | Type | Notes |
|---|---|---|
| `suite` | string | Suite name, e.g. `core`, `german`, `negative` |
| `question` | string | The Ask |
| `expected_clauses` | string[] | `clause_path`s that MUST be retrieved (empty for must-abstain cases) |
| `expected_facts` | string[] | Optional facts the answer should contain (default `[]`) |
| `must_abstain` | boolean | `true` for negative/out-of-corpus cases (default `false`) |
| `language` | string | `en` (default) or `de` |

Example line (do not add to a suite until every expected clause is manually
verified against the PDF — spec §8, P2):

```json
{"suite": "core", "question": "What does §25.1309(b) require for catastrophic failure conditions?", "expected_clauses": ["14 CFR Part 25 §25.1309"], "expected_facts": [], "must_abstain": false, "language": "en"}
```

A negative case:

```json
{"suite": "negative", "question": "What does DO-178C say about MC/DC coverage?", "expected_clauses": [], "expected_facts": [], "must_abstain": true, "language": "en"}
```

## Metrics per Case (spec §8)

- **recall@5 / recall@10 / MRR** over `expected_clauses`.
- **citation_precision** — cited clauses ⊆ relevant.
- **faithfulness** — LLM-judge: does each cited chunk entail its claim? (judge
  model ≠ answer model).
- **abstention correctness** — for negative cases, did the system abstain?

## Run mechanics (spec §8, arrives Week 3)

```bash
groundcite eval run --suite core   # writes eval_runs + prints table + evals/reports/<sha>.md
```

- Config snapshot is stored per Run so Runs are comparable.
- **CI gate:** a 12-case smoke suite fails the PR if recall@5 drops >5 pts vs.
  `evals/baseline.json`.
- **Honesty rule:** the README benchmark table shows current real numbers,
  including the embarrassing first baseline. The blog narrative is the
  *improvement* — which requires committing the bad baseline.

`evals/reports/` is git-ignored (generated per Run); suites and the baseline are
committed.

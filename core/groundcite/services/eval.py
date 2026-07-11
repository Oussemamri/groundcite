"""EvalService — the differentiator; build before the UI (spec §8).

Implements spec §8: run a Suite of Cases, compute recall@5/@10, MRR,
citation_precision, faithfulness (LLM-judge; judge model != answer model), and
abstention correctness; persist eval_runs/eval_results and write the report.
Not yet implemented (Week 3). Depends on AskService + the repository + a judge
LLM port.
"""

from __future__ import annotations


class EvalService:
    """Run eval Suites and score each Case (spec §8)."""

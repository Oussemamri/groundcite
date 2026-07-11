"""Answerer / judge prompts (spec §7 generation contract, §8 faithfulness judge).

The answerer system prompt (answer ONLY from chunks; every factual sentence maps
to >=1 citation; set ``insufficient: true`` when chunks lack the answer; reply in
the question's language; clause IDs verbatim) lives here as versioned text.
Populated in Week 3.
"""

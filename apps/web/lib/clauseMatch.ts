/**
 * Clause matching for the `/evals` drill-down's expected-vs-cited highlight
 * (spec §10 "retrieved-vs-expected clauses"; Week 5 AD-3).
 *
 * Mirrors `core/groundcite/services/metrics.py`'s `matches()` EXACTLY: a
 * golden case names a clause NUMBER ("25.1309") while a cited clause carries
 * a full clause_path ("14 CFR Part 25 §25.1309(b)"). A cited clause counts as
 * covering an expected one when its id is that clause OR a sub-paragraph of
 * it (equality, or a literal "(" immediately after the expected id -- so
 * "25.130" or "25.13099" do NOT bleed into a match for "25.13").
 *
 * This is presentational only -- it recomputes nothing the API already
 * scored (recall_at_5/citation_precision stay server-computed, rule 4); it
 * just decides which clause chips render as a hit for a human eyeballing the
 * drill-down, using the one documented matching rule the metrics themselves
 * use, not a UI-invented approximation.
 */

export function clauseIdOf(clausePath: string): string {
  const idx = clausePath.lastIndexOf("§");
  return (idx === -1 ? clausePath : clausePath.slice(idx + 1)).trim();
}

export function clausesMatch(citedClausePath: string, expectedClause: string): boolean {
  const cited = clauseIdOf(citedClausePath);
  const expected = clauseIdOf(expectedClause);
  return cited === expected || cited.startsWith(`${expected}(`);
}

/** True when at least one cited clause covers `expectedClause`. */
export function expectedClauseIsHit(expectedClause: string, citedClauses: string[]): boolean {
  return citedClauses.some((c) => clausesMatch(c, expectedClause));
}

/** True when `citedClause` covers at least one expected clause (relevant citation). */
export function citedClauseIsRelevant(citedClause: string, expectedClauses: string[]): boolean {
  return expectedClauses.some((e) => clausesMatch(citedClause, e));
}

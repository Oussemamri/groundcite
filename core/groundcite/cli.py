"""GroundCite CLI (Typer) — same services as the API (spec §9).

Commands (spec §9): ``groundcite ingest <pdf> --slug far-25``,
``groundcite ask "..." [--json]``, ``groundcite eval run --suite core``,
``groundcite eval report <run-id>``. The CLI is an interface-layer entry point:
it builds services via ``container.build_services`` and calls them.
"""

from __future__ import annotations

import json as json_lib
import subprocess
from pathlib import Path
from typing import cast

import typer

from groundcite.adapters.evalsuite.jsonl_suite import SuiteNotFoundError
from groundcite.config import get_settings
from groundcite.container import build_services
from groundcite.domain.entities import DocumentMeta
from groundcite.domain.results import (
    AskEvent,
    AskEventType,
    AskStatus,
    IngestionReport,
    RetrievalEvalReport,
    RetrievalResult,
)

app = typer.Typer(
    name="groundcite",
    help="Grounded Q&A over aerospace & engineering standards.",
    no_args_is_help=True,
    add_completion=False,
)

eval_app = typer.Typer(help="Eval Suite / Case / Run commands (spec §8).", no_args_is_help=True)
app.add_typer(eval_app, name="eval")

_NOT_IMPLEMENTED = "Not implemented in the P5 skeleton — arrives in a later milestone."


@app.command()
def ingest(
    pdf: str = typer.Argument(..., help="Path to a text-layer PDF to ingest (spec §6)"),
    slug: str = typer.Option(..., help="Document slug, e.g. far-25"),
    code: str = typer.Option(..., "--code", help="Standard code, e.g. '14 CFR Part 25'"),
    org: str = typer.Option(..., "--org", help="Issuing organization, e.g. FAA"),
    title: str = typer.Option(None, "--title", help="Document title (defaults to the code)"),
    source_url: str = typer.Option(None, "--source-url", help="Official source URL"),
    license_note: str = typer.Option(
        "US public domain", "--license", help="Redistribution/license note (spec §13)"
    ),
    skip_embeddings: bool = typer.Option(
        None,
        "--skip-embeddings/--no-skip-embeddings",
        help="Dry-run: zero-vector embeddings (overrides SKIP_EMBEDDINGS env)",
    ),
) -> None:
    """Ingest a text-layer PDF into the clause hierarchy (spec §6)."""
    pdf_path = Path(pdf)
    if not pdf_path.is_file():
        typer.secho(f"PDF not found: {pdf_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    settings = get_settings()
    if skip_embeddings is not None:
        settings = settings.model_copy(update={"skip_embeddings": skip_embeddings})

    services = build_services(settings)
    meta = DocumentMeta(
        slug=slug,
        standard_code=code,
        title=title or code,
        organization=org,
        license_note=license_note,
        source_url=source_url,
    )
    report = services.ingestion.ingest(pdf_path, meta)
    typer.echo(_format_report(report))


def _format_report(r: IngestionReport) -> str:
    lines = [
        "Ingestion report — spec §6 step 5",
        "================================",
        f"slug            : {r.slug}",
        f"standard_code   : {r.standard_code}",
        f"document_id     : {r.document_id}",
        f"sections found  : {r.sections_found}",
        f"chunks created  : {r.chunks_created}",
        f"attached text   : {r.attached_pct:.1%}",
        f"orphan text     : {r.orphan_pct:.1%}  (Week-1 DoD: <10%)",
        f"total text chars: {r.total_text_chars}",
        "token histogram :",
    ]
    for bucket, count in r.token_histogram.items():
        bar = "#" * min(40, count)
        lines.append(f"  {bucket:>8} : {count:5d}  {bar}")
    return "\n".join(lines)


@app.command()
def ask(
    question: str,
    json_out: bool = typer.Option(False, "--json", help="Emit JSON"),
    slug: list[str] = typer.Option(None, "--slug", help="Restrict to document slug(s)"),
    top_k: int = typer.Option(None, "--top-k", help="Passages to show (default CONTEXT_K=6)"),
    rerank: bool = typer.Option(
        None, "--rerank/--no-rerank", help="Override RERANKER_ENABLED for this ask"
    ),
    retrieval_only: bool = typer.Option(
        False,
        "--retrieval-only",
        help="Skip generation; print ranked passages only (spec §15 Week 2 mode)",
    ),
) -> None:
    """Ask a grounded question (spec §7).

    Full mode (default, Week 3): retrieval → Gates A/B → streamed generation →
    citations. Requires an LLM provider and RERANKER_ENABLED=true (Gate A needs
    the normalized reranker score — AD-3). ``--retrieval-only`` runs just the
    Week-2 retrieval half and prints ranked passages with scores, no LLM call.
    """
    settings = get_settings()
    if rerank is not None:
        settings = settings.model_copy(update={"reranker_enabled": rerank})

    services = build_services(settings)

    if retrieval_only:
        result = services.ask.retrieve(question, document_slugs=slug or None, top_k=top_k)
        if json_out:
            typer.echo(result.model_dump_json(indent=2))
            return
        typer.echo(_format_retrieval(result))
        return

    events = list(services.ask.ask(question, document_slugs=slug or None))
    terminal = next(
        (e for e in reversed(events) if e.type in (AskEventType.FINAL, AskEventType.ERROR)),
        None,
    )
    if json_out:
        typer.echo(json_lib.dumps(terminal.data if terminal else {}, indent=2))
        return

    typer.echo(f"Q: {question}")
    for event in events:
        if event.type is AskEventType.STAGE:
            typer.echo(f"   [{event.data['stage']}]")
        elif event.type is AskEventType.TOKEN:
            typer.echo(str(event.data["token"]), nl=False)
    typer.echo()
    typer.echo()
    typer.echo(_format_final(terminal) if terminal else "(no terminal event — this is a bug)")


def _format_final(event: AskEvent) -> str:
    """Render the terminal FINAL/ERROR event of a full-mode ask() (spec §7).

    ``event.data`` is ``dict[str, object]`` (the SSE contract's type, shared with
    apps/api); the nested shapes here are guaranteed by ``AskService.ask`` in the
    SAME process (``Answer``/``Abstention``/``Citation``/``RetrievedChunk``
    ``model_dump(mode="json")``), so a ``cast`` — not a defensive re-validation —
    is the honest way to display them.
    """
    if event.type is AskEventType.ERROR:
        return f"ERROR: {event.data['message']}"

    status = str(event.data["status"])
    lines = [f"status: {status.upper()}"]
    if status == AskStatus.GROUNDED.value:
        answer = cast(dict[str, object], event.data["answer"])
        lines += ["", str(answer["answer_md"]), "", "citations:"]
        for raw_c in cast(list[dict[str, object]], answer["citations"]):
            label = raw_c.get("clause_path") or raw_c["chunk_id"]
            score = cast(float, raw_c["score"])
            lines.append(f"  [{raw_c['rank']}] {label}  score={score:.4f}")
    else:
        abstention = cast(dict[str, object], event.data["abstention"])
        lines.append(f"reason: {abstention['reason']}")
        passages = cast(list[dict[str, object]], abstention.get("top_passages") or [])
        if passages:
            lines += ["", "closest passages:"]
            for p in passages:
                lines.append(f"  {p['clause_path']}  score={cast(float, p['score']):.4f}")
    lines += ["", f"latency: {event.data['latency_ms']}ms   ask_id: {event.data['ask_id']}"]
    return "\n".join(lines)


def _format_retrieval(r: RetrievalResult) -> str:
    stage = "fused+reranked" if r.reranked else "fused (no rerank)"
    lines = [
        f"Q: {r.question}",
        f"   clause fast-path: {', '.join(r.clause_ids) if r.clause_ids else '(none detected)'}",
        f"   stage: {stage}   passages: {len(r.chunks)}",
        "",
        f"{'#':>2}  {'score':>7}  clause_path",
        f"{'-' * 2}  {'-' * 7}  {'-' * 60}",
    ]
    for i, chunk in enumerate(r.chunks, 1):
        lines.append(f"{i:>2}  {chunk.score:>7.4f}  {chunk.clause_path}")
        lines.append(f"        {_snippet(chunk.content)}")
    return "\n".join(lines)


def _snippet(content: str, width: int = 88) -> str:
    """One-line preview: the chunk body after its breadcrumb header (spec §6)."""
    body = content.split("\n", 1)[-1] if "\n" in content else content
    flat = " ".join(body.split())
    return flat[:width] + ("…" if len(flat) > width else "")


@eval_app.command("run")
def eval_run(
    suite: str = typer.Option("core", help="Suite name, e.g. core"),
    slug: list[str] = typer.Option(None, "--slug", help="Restrict retrieval to document slug(s)"),
    rerank: bool = typer.Option(
        None, "--rerank/--no-rerank", help="Override RERANKER_ENABLED for this run"
    ),
    write_report: bool = typer.Option(
        True, "--write-report/--no-write-report", help="Write evals/reports/<sha>.md (spec §8)"
    ),
) -> None:
    """Run an eval Suite and write a report (spec §8).

    Week 2 is RETRIEVAL-ONLY (spec §15.1): recall@5 / recall@10 / MRR, computed
    with no LLM and no judge. Faithfulness and citation precision arrive in Week 3.
    """
    settings = get_settings()
    if rerank is not None:
        settings = settings.model_copy(update={"reranker_enabled": rerank})

    services = build_services(settings)
    git_sha = _git_sha()
    config_snapshot: dict[str, object] = {
        "embedding_model": settings.embedding_model,
        "reranker_enabled": settings.reranker_enabled,
        "reranker_model": settings.reranker_model if settings.reranker_enabled else None,
        "rrf_k": settings.rrf_k,
        "candidates_dense": settings.candidates_dense,
        "candidates_lexical": settings.candidates_lexical,
        "fused_k": settings.fused_k,
        "context_k": settings.context_k,
    }

    try:
        report = services.evals.run_retrieval(
            suite,
            git_sha=git_sha,
            document_slugs=slug or None,
            config=config_snapshot,
        )
    except SuiteNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    typer.echo(_format_eval(report))
    if write_report:
        path = _write_eval_report(report, settings.eval_reports_dir)
        typer.echo(f"\nreport written: {path}")


def _format_eval(r: RetrievalEvalReport) -> str:
    rerank_note = "on" if r.reranked else "off"
    lines = [
        f"Retrieval eval — suite '{r.suite}' (spec §8, retrieval-only)",
        "=" * 60,
        f"git sha        : {r.git_sha}",
        f"reranker       : {rerank_note}",
        f"scored cases   : {r.scored_cases}",
        f"must-abstain   : {r.must_abstain_cases}  (not scored here — Gate A is Week 3)",
        "",
        f"{'metric':<14} {'value':>8}",
        f"{'-' * 14} {'-' * 8}",
        f"{'recall@5':<14} {r.recall_at_5:>8.3f}",
        f"{'recall@10':<14} {r.recall_at_10:>8.3f}",
        f"{'MRR':<14} {r.mrr:>8.3f}",
        "",
        "misses (recall@10 = 0):",
    ]
    misses = [
        c for c in r.cases if not c.must_abstain and c.expected_clauses and not c.recall_at_10
    ]
    if not misses:
        lines.append("  (none)")
    for case in misses:
        lines.append(f"  expected {', '.join(case.expected_clauses):<22} {case.question[:60]}")
    return "\n".join(lines)


def _write_eval_report(r: RetrievalEvalReport, reports_dir: Path) -> Path:
    """Write evals/reports/<sha>.md (spec §8 run mechanics)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{r.git_sha}-{r.suite}-retrieval.md"
    lines = [
        f"# Retrieval eval — `{r.suite}` @ `{r.git_sha}`",
        "",
        "Retrieval-only (spec §8 / §15.1): recall@k and MRR, no judge, no LLM.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| recall@5 | {r.recall_at_5:.3f} |",
        f"| recall@10 | {r.recall_at_10:.3f} |",
        f"| MRR | {r.mrr:.3f} |",
        f"| scored cases | {r.scored_cases} |",
        f"| must-abstain cases (unscored) | {r.must_abstain_cases} |",
        "",
        "## Config snapshot",
        "",
        "```json",
        json_lib.dumps(r.config, indent=2, sort_keys=True),
        "```",
        "",
        "## Per-case",
        "",
        "| # | expected | hit rank | r@5 | r@10 | question |",
        "|---|---|---|---|---|---|",
    ]
    for i, c in enumerate((x for x in r.cases if not x.must_abstain), 1):
        hit = str(c.first_hit_rank) if c.first_hit_rank else "—"
        lines.append(
            f"| {i} | `{', '.join(c.expected_clauses)}` | {hit} | "
            f"{c.recall_at_5:.2f} | {c.recall_at_10:.2f} | {c.question[:70]} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return "unknown"


@eval_app.command("report")
def eval_report(run_id: str) -> None:
    """Print the report for a past eval Run (spec §8)."""
    raise typer.Exit(_exit_stub("eval report"))


def _exit_stub(command: str) -> int:
    typer.secho(f"`groundcite {command}`: {_NOT_IMPLEMENTED}", fg=typer.colors.YELLOW, err=True)
    return 1


if __name__ == "__main__":
    app()

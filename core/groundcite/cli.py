"""GroundCite CLI (Typer) — same services as the API (spec §9).

Commands (spec §9): ``groundcite ingest <pdf> --slug far-25``,
``groundcite ask "..." [--json]``, ``groundcite eval run --suite core``,
``groundcite eval report <run-id>``. The CLI is an interface-layer entry point:
it builds services via ``container.build_services`` and calls them. P5 wires the
Typer app and command shells; command bodies land with their services.
"""

from __future__ import annotations

import typer

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
def ingest(pdf: str, slug: str = typer.Option(..., help="Document slug, e.g. far-25")) -> None:
    """Ingest a text-layer PDF into the clause hierarchy (spec §6)."""
    raise typer.Exit(_exit_stub("ingest"))


@app.command()
def ask(question: str, json: bool = typer.Option(False, help="Emit JSON")) -> None:
    """Ask a grounded question (spec §7)."""
    raise typer.Exit(_exit_stub("ask"))


@eval_app.command("run")
def eval_run(suite: str = typer.Option("core", help="Suite name, e.g. core")) -> None:
    """Run an eval Suite and write a report (spec §8)."""
    raise typer.Exit(_exit_stub("eval run"))


@eval_app.command("report")
def eval_report(run_id: str) -> None:
    """Print the report for a past eval Run (spec §8)."""
    raise typer.Exit(_exit_stub("eval report"))


def _exit_stub(command: str) -> int:
    typer.secho(f"`groundcite {command}`: {_NOT_IMPLEMENTED}", fg=typer.colors.YELLOW, err=True)
    return 1


if __name__ == "__main__":
    app()

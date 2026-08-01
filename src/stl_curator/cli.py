from __future__ import annotations

from pathlib import Path

import typer

from stl_curator.config import load_config
from stl_curator.pipeline import ingest as run_ingest
from stl_curator.pipeline import rebuild_cache as rebuild_cache_fn

app = typer.Typer(help="STL library curator")


@app.callback()
def _main() -> None:
    """STL library curator.

    An empty callback keeps `ingest` registered as an explicit subcommand
    instead of Typer collapsing the single command into the app root
    (which would otherwise swallow "ingest" as the positional `root` value).
    """


@app.command()
def ingest(
    root: Path | None = typer.Argument(None, help="Store root (default: config)"),  # noqa: B008
    config: Path = typer.Option(Path("config.toml"), "--config"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    cfg = load_config(config, store_root=root)
    s = run_ingest(cfg, dry_run=dry_run)
    for k, v in vars(s).items():
        typer.echo(f"{k:18} {v}")


@app.command("rebuild-cache")
def rebuild(config: Path = typer.Option(Path("config.toml"), "--config")):  # noqa: B008
    cfg = load_config(config)
    n = rebuild_cache_fn(cfg)
    typer.echo(f"restored {n} groups from vault")


if __name__ == "__main__":
    app()

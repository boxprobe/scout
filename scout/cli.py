"""Click CLI entry point (Wrangler-style unified entry)."""

import click


@click.group()
@click.version_option()
def main() -> None:
    """Scout — Black-box testing, pinpoint precision."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--headless/--headed",
    default=True,
    help="Run browser headless (default) or headed.",
)
@click.option("--env", "env_name", default=None, help="Environment name to tag this run.")
def run(path: str, headless: bool, env_name: str | None) -> None:
    """Run a test scenario file."""
    import asyncio
    from pathlib import Path

    from scout.config import load_config
    from scout.git import git_info
    from scout.index import IndexDB
    from scout.run_metadata import build_metadata
    from scout.runner import execute_file

    result = asyncio.run(execute_file(path, headless=headless))

    # Record metadata regardless of pass/fail
    config = load_config(Path("scout.yml"))
    git = git_info()
    meta = build_metadata(config=config, git=git, scenario=path, env=env_name)
    db = IndexDB(config.data_dir / "index.db")
    db.insert(meta)
    db.close()

    if result.success:
        click.echo(f"PASSED: {path} (run_id: {meta.run_id})")
    else:
        click.echo(f"FAILED: {path} (run_id: {meta.run_id})", err=True)
        for err in result.errors:
            click.echo(f"  {err}", err=True)
        raise SystemExit(1)


@main.command()
@click.option("--app", default=None, help="Filter by app name.")
@click.option("--scenario", default=None, help="Filter by scenario path.")
@click.option("--app-version", "app_version", default=None, help="Filter by app version.")
@click.option("--env", "env_name", default=None, help="Filter by environment name.")
def runs(
    app: str | None,
    scenario: str | None,
    app_version: str | None,
    env_name: str | None,
) -> None:
    """List recorded test runs."""
    from pathlib import Path

    from scout.config import load_config
    from scout.index import IndexDB

    config = load_config(Path("scout.yml"))
    index_path = config.data_dir / "index.db"

    if not index_path.exists():
        click.echo("No runs found.")
        return

    db = IndexDB(index_path)
    rows = db.query(app=app, scenario=scenario, app_version=app_version, env=env_name)
    db.close()

    if not rows:
        click.echo("No runs found.")
        return

    for row in rows:
        parts = [
            row["run_id"],
            row["timestamp"],
            row["app"] or "-",
            row["scenario"] or "-",
            row["env"] or "-",
        ]
        click.echo("  ".join(parts))


@main.command()
def report() -> None:
    """Generate comparison report from recorded data."""
    click.echo("scout report: not yet implemented")


@main.command()
def proxy() -> None:
    """Start/stop the recording proxy."""
    click.echo("scout proxy: not yet implemented")


@main.command()
def upload() -> None:
    """Upload recordings to object storage."""
    click.echo("scout upload: not yet implemented")


@main.command(name="mcp-server")
def mcp_server() -> None:
    """Start MCP Server for AI Agent integration."""
    click.echo("scout mcp-server: not yet implemented")

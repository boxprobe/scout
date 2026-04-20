"""Click CLI entry point (Wrangler-style unified entry)."""

import click


@click.group()
@click.version_option()
def main() -> None:
    """Scout — Black-box testing, pinpoint precision."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--headless/--headed", default=True, help="Run browser headless (default) or headed.")
def run(path: str, headless: bool) -> None:
    """Run a test scenario file."""
    import asyncio

    from scout.runner import execute_file

    result = asyncio.run(execute_file(path, headless=headless))
    if result.success:
        click.echo(f"PASSED: {path}")
    else:
        click.echo(f"FAILED: {path}", err=True)
        for err in result.errors:
            click.echo(f"  {err}", err=True)
        raise SystemExit(1)


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
    """Upload results to Argus Server."""
    click.echo("scout upload: not yet implemented")


@main.command(name="mcp-server")
def mcp_server() -> None:
    """Start MCP Server for AI Agent integration."""
    click.echo("scout mcp-server: not yet implemented")

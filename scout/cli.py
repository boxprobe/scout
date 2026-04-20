"""Click CLI entry point (Wrangler-style unified entry)."""

import click


@click.group()
@click.version_option()
def main() -> None:
    """Scout — Black-box testing, pinpoint precision."""


@main.command()
def run() -> None:
    """Run test scenarios."""
    click.echo("scout run: not yet implemented")


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

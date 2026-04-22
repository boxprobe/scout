"""Scout CLI — Black-box testing, pinpoint precision."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import click
import httpx

from scout.config import load_app_config
from scout.git import git_info
from scout.runner.executor import _find_worktree_root, execute_batch


def _resolve_test_paths(paths: tuple[str, ...]) -> list[str]:
    """Expand directories to test.py files, pass files through."""
    result: list[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            result.extend(str(f) for f in sorted(path.rglob("test.py")))
        elif path.is_file():
            result.append(str(path))
        else:
            click.echo(f"Warning: skipping {p} (not found)", err=True)
    return result


def _find_repo_root(paths: list[str]) -> Path:
    """Find the delivery repo root (directory containing app.json)."""
    if paths:
        root = _find_worktree_root(Path(paths[0]))
        if root:
            return root
    return Path.cwd()


@click.group()
@click.version_option()
def main() -> None:
    """Scout — Black-box testing, pinpoint precision."""


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--headless/--headed", default=True, help="Run headless (default) or headed.")
@click.option("--proxy", default=None, help="Recording proxy address (e.g. localhost:8080).")
@click.option("--env", "env_name", default=None, help="Environment name.")
@click.option("--out", "out_dir", default=None, type=click.Path(), help="Output directory.")
def run(
    paths: tuple[str, ...],
    headless: bool,
    proxy: str | None,
    env_name: str | None,
    out_dir: str | None,
) -> None:
    """Run test scenarios (production mode)."""
    test_paths = _resolve_test_paths(paths)
    if not test_paths:
        click.echo("No test files found.", err=True)
        raise SystemExit(1)

    repo_root = _find_repo_root(test_paths)
    config = load_app_config(repo_root)
    git = git_info(repo_root)
    run_id = str(uuid.uuid4())[:8]

    if out_dir:
        runs_dir = Path(out_dir)
    else:
        runs_dir = repo_root / ".scout" / "runs" / run_id

    # Derive control port from proxy address
    control_port = None
    if proxy:
        proxy_host = proxy.split(":")[0] or "127.0.0.1"
        control_port = 8081  # default control port
        # Check proxy reachability
        try:
            resp = httpx.get(f"http://{proxy_host}:{control_port}/session/status", timeout=3)
            resp.raise_for_status()
        except Exception:
            click.echo(
                f"Error: Recording proxy not reachable at {proxy_host}:{control_port}",
                err=True,
            )
            raise SystemExit(1)

    # Build proxy session callbacks
    on_before = None
    on_after = None
    if proxy and control_port:
        proxy_host = proxy.split(":")[0] or "127.0.0.1"
        control_base = f"http://{proxy_host}:{control_port}"
        record_db = str(runs_dir / "record.db")

        async def on_before(scenario_path: str) -> None:  # type: ignore[no-redef]
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{control_base}/session/start",
                    json={
                        "scenario": scenario_path,
                        "run_id": run_id,
                        "db_path": record_db,
                        "api_base_url": config.api_base_url,
                    },
                )

        async def on_after(scenario_path: str, result) -> None:  # type: ignore[no-redef]
            async with httpx.AsyncClient() as client:
                await client.post(f"{control_base}/session/stop")

    results = asyncio.run(
        execute_batch(
            test_paths,
            headless=headless,
            results_dir=runs_dir,
            screenshots=False,
            proxy=proxy,
            on_before_scenario=on_before,
            on_after_scenario=on_after,
        )
    )

    # Generate reports
    from scout.report.html import generate_html
    from scout.report.junit import generate_junit

    generate_junit(results, runs_dir / "junit.xml", run_id=run_id)
    generate_html(results, runs_dir / "report.html", run_id=run_id, app_name=config.name)

    # Record to index
    from scout.index import IndexDB
    from scout.run_metadata import RunMetadata, build_metadata

    index = IndexDB(repo_root / ".scout" / "index.db")
    for scenario_path, result in results.items():
        meta = build_metadata(config=config, git=git, scenario=scenario_path, env=env_name)
        # Override run_id to use our batch run_id
        meta = RunMetadata(
            run_id=run_id,
            timestamp=meta.timestamp,
            scenario=scenario_path,
            app=meta.app,
            app_version=meta.app_version,
            env=meta.env,
            commit=meta.commit,
            branch=meta.branch,
            scout_version=meta.scout_version,
        )
        index.insert(meta)
    index.close()

    # Summary
    passed = sum(1 for r in results.values() if r.success)
    failed = len(results) - passed

    for scenario_path, result in results.items():
        status = "PASSED" if result.success else "FAILED"
        click.echo(f"  {status}: {scenario_path} ({result.duration_ms}ms)")
        for err in result.errors:
            click.echo(f"    {err}", err=True)

    click.echo(f"\n{passed} passed, {failed} failed")
    click.echo(f"Report: {runs_dir / 'report.html'}")
    click.echo(f"JUnit:  {runs_dir / 'junit.xml'}")

    if failed > 0:
        raise SystemExit(1)


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--headless/--headed", default=False, help="Run headed (default) or headless.")
@click.option(
    "--screenshots/--no-screenshots", default=True,
    help="Take before/after screenshots (default: yes).",
)
@click.option("--out", "out_dir", default=None, type=click.Path(), help="Output directory.")
def verify(
    paths: tuple[str, ...],
    headless: bool,
    screenshots: bool,
    out_dir: str | None,
) -> None:
    """Verify scenarios (debug mode with screenshots)."""
    test_paths = _resolve_test_paths(paths)
    if not test_paths:
        click.echo("No test files found.", err=True)
        raise SystemExit(1)

    repo_root = _find_repo_root(test_paths)

    if out_dir:
        results_dir = Path(out_dir)
    else:
        results_dir = repo_root / ".scout" / "results"

    results = asyncio.run(
        execute_batch(
            test_paths,
            headless=headless,
            results_dir=results_dir,
            screenshots=screenshots,
        )
    )

    passed = sum(1 for r in results.values() if r.success)
    failed = len(results) - passed

    for scenario_path, result in results.items():
        status = "PASSED" if result.success else "FAILED"
        click.echo(f"  {status}: {scenario_path} ({result.duration_ms}ms)")
        for err in result.errors:
            click.echo(f"    {err}", err=True)

    click.echo(f"\n{passed} passed, {failed} failed")
    if failed > 0:
        raise SystemExit(1)


@main.command()
@click.option("--port", default=8080, help="Proxy listen port.")
@click.option("--control-port", default=8081, help="Control API port.")
def record(port: int, control_port: int) -> None:
    """Start the recording proxy.

    DB path and API filter are provided per-run via /session/start.
    """
    from scout.collector.control import ControlServer

    control = ControlServer(port=control_port)

    click.echo(f"Recording proxy: :{port}")
    click.echo(f"Control API:     :{control_port}")
    click.echo("Waiting for session/start from scout run...")

    async def _run_proxy() -> None:
        await control.start()

        from mitmproxy.options import Options
        from mitmproxy.tools.dump import DumpMaster

        from scout.collector.proxy import RecordingAddon

        opts = Options(listen_host="0.0.0.0", listen_port=port)
        master = DumpMaster(opts)
        master.addons.add(RecordingAddon(control))

        try:
            await master.run()
        finally:
            await control.stop()

    try:
        asyncio.run(_run_proxy())
    except KeyboardInterrupt:
        click.echo("\nStopped.")


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
    from scout.index import IndexDB

    index_path = Path.cwd() / ".scout" / "index.db"
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
def upload() -> None:
    """Upload recordings to object storage."""
    click.echo("scout upload: not yet implemented")


@main.command()
def analyze() -> None:
    """Analyze API recordings for regression detection."""
    click.echo("scout analyze: not yet implemented")

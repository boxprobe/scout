"""Scout CLI — Black-box testing, pinpoint precision."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx

from importlib.metadata import PackageNotFoundError, version

from scout.config import load_app_config
from scout.git import git_info
from scout.runner.executor import _find_worktree_root, execute_batch


def _scout_version() -> str:
    try:
        return version("scout")
    except PackageNotFoundError:
        return "dev"


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
@click.option("--env", "env_name", default=None, help="Environment name.")
@click.option("--out", "out_dir", default=None, type=click.Path(), help="Output directory.")
def run(
    paths: tuple[str, ...],
    headless: bool,
    env_name: str | None,
    out_dir: str | None,
) -> None:
    """Run test scenarios with API recording."""
    from scout.collector.subprocess import ProxyProcess

    test_paths = _resolve_test_paths(paths)
    if not test_paths:
        click.echo("No test files found.", err=True)
        raise SystemExit(1)

    repo_root = _find_repo_root(test_paths)
    config = load_app_config(repo_root)
    git = git_info(repo_root)
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

    if out_dir:
        runs_dir = Path(out_dir)
    else:
        runs_dir = repo_root / ".scout" / "runs" / run_id

    # Start recording proxy
    proxy_proc = ProxyProcess()
    try:
        proxy_proc.start()
    except RuntimeError:
        click.echo("Error: failed to start recording proxy", err=True)
        raise SystemExit(1)

    proxy = proxy_proc.proxy_addr
    control_base = proxy_proc.control_base
    record_db = str(runs_dir / "record.db")

    async def on_before(scenario_path: str) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{control_base}/session/start",
                json={
                    "scenario": scenario_path,
                    "run_id": run_id,
                    "db_path": record_db,
                    "api_base_url": config.api_base_url,
                    "app": config.name,
                    "app_version": config.app_version,
                    "env": env_name,
                    "commit_hash": git.commit,
                    "branch": git.branch,
                    "scout_version": _scout_version(),
                },
            )

    async def on_after(scenario_path: str, result) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(f"{control_base}/session/stop")

    try:
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
    finally:
        proxy_proc.stop()

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


@main.command()
@click.argument("baseline", required=True)
@click.argument("target", required=True)
@click.option("--detail/--no-detail", default=False, help="Include raw request/response data in diff.")
def diff(baseline: str, target: str, detail: bool) -> None:
    """Compare API recordings between two runs."""
    from scout.collector.db import RecordingDB
    from scout.matcher.align import align_records
    from scout.matcher.compare import compare_pair
    from scout.matcher.diff_db import DiffDB
    from scout.matcher.diff_report import generate_diff_html

    repo_root = Path.cwd()
    scout_dir = repo_root / ".scout"

    # Find record.db files
    base_db_path = scout_dir / "runs" / baseline / "record.db"
    target_db_path = scout_dir / "runs" / target / "record.db"

    if not base_db_path.exists():
        click.echo(f"Error: baseline record.db not found: {base_db_path}", err=True)
        raise SystemExit(1)
    if not target_db_path.exists():
        click.echo(f"Error: target record.db not found: {target_db_path}", err=True)
        raise SystemExit(1)

    base_rdb = RecordingDB(base_db_path)
    target_rdb = RecordingDB(target_db_path)

    # Read scenarios
    base_sessions = base_rdb.get_all_sessions()
    target_sessions = target_rdb.get_all_sessions()

    if not base_sessions or not target_sessions:
        click.echo("Error: no recording sessions found in one or both runs.", err=True)
        raise SystemExit(1)

    base_s = dict(base_sessions[0])
    target_s = dict(target_sessions[0])

    # Validate app + scenario match
    if base_s.get("app") != target_s.get("app"):
        click.echo(
            f"Error: app mismatch — baseline '{base_s.get('app')}' vs target '{target_s.get('app')}'",
            err=True,
        )
        raise SystemExit(1)
    if base_s.get("scenario") != target_s.get("scenario"):
        click.echo(
            f"Error: scenario mismatch — baseline '{base_s.get('scenario')}' vs target '{target_s.get('scenario')}'",
            err=True,
        )
        raise SystemExit(1)

    # Load records
    base_records = base_rdb.get_api_records(base_s["id"])
    target_records = target_rdb.get_api_records(target_s["id"])
    base_rdb.close()
    target_rdb.close()

    # Align
    aligned = align_records(base_records, target_records)

    # Compare + write results
    diff_dir = scout_dir / "diffs" / f"{baseline}_vs_{target}"
    ddb = DiffDB(diff_dir / "diff.db")
    ddb.set_meta(
        baseline_run_id=baseline,
        target_run_id=target,
        app=base_s.get("app") or "",
        scenario=base_s.get("scenario") or "",
    )

    def _detail_kwargs(rec: dict, prefix: str) -> dict:
        """Extract raw data kwargs for insert_endpoint_diff when --detail."""
        if not detail:
            return {}
        return {
            f"{prefix}_url": rec.get("url"),
            f"{prefix}_request": rec.get("request_body"),
            f"{prefix}_response": rec.get("response_body"),
            f"{prefix}_timestamp": rec.get("timestamp"),
            f"{prefix}_duration": rec.get("duration_ms"),
        }

    for pair in aligned:
        if pair.baseline is not None and pair.target is not None:
            result = compare_pair(pair.baseline, pair.target)
            ddb.insert_endpoint_diff(
                baseline_record_id=pair.baseline.get("id"),
                target_record_id=pair.target.get("id"),
                method=pair.method,
                path=pair.path,
                status_match=result.status_match,
                baseline_status=result.baseline_status,
                target_status=result.target_status,
                structure_match=result.structure_match,
                diff_summary=result.diff_summary,
                value_match=result.value_match,
                value_diff=result.value_diff,
                **_detail_kwargs(pair.baseline, "baseline"),
                **_detail_kwargs(pair.target, "target"),
            )
        elif pair.baseline is not None:
            ddb.insert_missing_endpoint(
                side="baseline",
                record_id=pair.baseline.get("id", 0),
                method=pair.method,
                path=pair.path,
                status_code=pair.baseline.get("status_code"),
            )
        elif pair.target is not None:
            ddb.insert_missing_endpoint(
                side="target",
                record_id=pair.target.get("id", 0),
                method=pair.method,
                path=pair.path,
                status_code=pair.target.get("status_code"),
            )

    # Generate report
    meta = ddb.get_meta()
    diffs = ddb.get_endpoint_diffs()
    missing = ddb.get_missing_endpoints()
    summary = ddb.summary()
    ddb.close()

    generate_diff_html(meta, diffs, missing, summary, diff_dir / "report.html")

    # Print summary
    has_issues = summary["status_mismatches"] + summary["structure_mismatches"] + summary["missing_endpoints"]
    value_changes = summary.get("value_mismatches", 0)
    if has_issues:
        click.echo(f"REGRESSION: {summary['status_mismatches']} status, "
                    f"{summary['structure_mismatches']} structure, "
                    f"{value_changes} value, "
                    f"{summary['missing_endpoints']} endpoint changes")
    elif value_changes:
        click.echo(f"SCHEMA_OK: {summary['total_paired']} endpoints, "
                    f"{value_changes} value changes")
    else:
        click.echo(f"OK: {summary['total_paired']} endpoints compared, no regression")

    click.echo(f"Report: {diff_dir / 'report.html'}")
    click.echo(f"Data:   {diff_dir / 'diff.db'}")

    if has_issues:
        raise SystemExit(1)

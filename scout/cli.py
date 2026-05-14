"""Scout CLI — Black-box testing, pinpoint precision."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import click
import httpx

from importlib.metadata import PackageNotFoundError, version

from scout.config import load_app_config, override_urls
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
@click.option("--web-base-url", default=None, help="Override web_base_url from app.json.")
@click.option("--api-base-url", default=None, help="Override api_base_url from app.json.")
@click.option("--web-version", default=None, help="Web app version label (e.g. 2.14.0).")
@click.option("--api-version", default=None, help="API version label (defaults to --web-version).")
@click.option("--web-commit", default=None, help="Web app commit hash.")
@click.option("--api-commit", default=None, help="API commit hash (defaults to --web-commit).")
@click.option("--concurrency", default=10, type=click.IntRange(1, 50),
              help="Max parallel scenarios (default: 10, max: 50).")
def run(
    paths: tuple[str, ...],
    headless: bool,
    env_name: str | None,
    out_dir: str | None,
    web_base_url: str | None,
    api_base_url: str | None,
    web_version: str | None,
    api_version: str | None,
    web_commit: str | None,
    api_commit: str | None,
    concurrency: int,
) -> None:
    """Run test scenarios with API recording."""
    from scout.collector.subprocess import ProxyProcess

    test_paths = _resolve_test_paths(paths)
    if not test_paths:
        click.echo("No test files found.", err=True)
        raise SystemExit(1)

    repo_root = _find_repo_root(test_paths)
    config = override_urls(load_app_config(repo_root), web_base_url, api_base_url)
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
        # Load step metadata from steps.json if available
        steps_data: list[dict] | None = None
        scenario_dir = repo_root / "scenarios" / scenario_path
        steps_file = scenario_dir / "steps.json"
        if steps_file.exists():
            import json
            steps_data = json.loads(steps_file.read_text(encoding="utf-8"))

        async with httpx.AsyncClient() as client:
            payload: dict = {
                "scenario": scenario_path,
                "run_id": run_id,
                "db_path": record_db,
                "api_base_url": config.api_base_url,
                "app": config.name,
                "web_version": web_version,
                "api_version": api_version or web_version,
                "env": env_name,
                "web_commit": web_commit,
                "api_commit": api_commit or web_commit,
                "scenario_commit": git.commit,
                "scout_version": _scout_version(),
            }
            if steps_data:
                payload["steps"] = steps_data
            await client.post(
                f"{control_base}/session/start",
                json=payload,
            )

    async def on_after(scenario_path: str, result) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{control_base}/session/stop",
                json={"scenario": scenario_path},
            )

    try:
        t_wall = time.monotonic()
        results = asyncio.run(
            execute_batch(
                test_paths,
                headless=headless,
                results_dir=runs_dir,
                screenshots=False,
                proxy=proxy,
                on_before_scenario=on_before,
                on_after_scenario=on_after,
                base_url_override=web_base_url,
                max_concurrency=concurrency,
            )
        )
        wall_ms = int((time.monotonic() - t_wall) * 1000)
    finally:
        proxy_proc.stop()

    # Generate reports
    from scout.report.html import generate_html
    from scout.report.junit import generate_junit

    generate_junit(results, runs_dir / "junit.xml", run_id=run_id)
    generate_html(results, runs_dir / "report.html", run_id=run_id, app_name=config.name,
                  wall_ms=wall_ms)

    # Record to index
    from scout.index import IndexDB
    from scout.run_metadata import RunMetadata, build_metadata

    index = IndexDB(repo_root / ".scout" / "index.db")
    for scenario_path, result in results.items():
        meta = build_metadata(
            config=config, git=git, scenario=scenario_path, env=env_name,
            web_version=web_version, api_version=api_version,
            web_commit=web_commit, api_commit=api_commit,
        )
        # Override run_id to use our batch run_id
        meta = RunMetadata(
            run_id=run_id,
            timestamp=meta.timestamp,
            scenario=scenario_path,
            app=meta.app,
            web_version=meta.web_version,
            api_version=meta.api_version,
            env=meta.env,
            web_commit=meta.web_commit,
            api_commit=meta.api_commit,
            scenario_commit=meta.scenario_commit,
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
@click.option("--headless/--headed", default=True, help="Run headless (default) or headed.")
@click.option(
    "--screenshots/--no-screenshots", default=True,
    help="Take before/after screenshots (default: yes).",
)
@click.option("--out", "out_dir", default=None, type=click.Path(), help="Output directory.")
@click.option("--web-base-url", default=None, help="Override web_base_url from app.json.")
@click.option("--api-base-url", default=None, help="Override api_base_url from app.json.")
def verify(
    paths: tuple[str, ...],
    headless: bool,
    screenshots: bool,
    out_dir: str | None,
    web_base_url: str | None,
    api_base_url: str | None,
) -> None:
    """Verify scenarios (debug mode with screenshots)."""
    import shutil

    test_paths = _resolve_test_paths(paths)
    if not test_paths:
        click.echo("No test files found.", err=True)
        raise SystemExit(1)

    repo_root = _find_repo_root(test_paths)

    if out_dir:
        results_dir = Path(out_dir)
    else:
        results_dir = repo_root / ".scout" / "results"

    # Clean previous results
    if results_dir.exists():
        shutil.rmtree(results_dir)

    t_wall = time.monotonic()
    results = asyncio.run(
        execute_batch(
            test_paths,
            headless=headless,
            results_dir=results_dir,
            screenshots=screenshots,
            base_url_override=web_base_url,
        )
    )
    wall_ms = int((time.monotonic() - t_wall) * 1000)

    # Generate verify report with screenshot gallery
    from scout.report.verify_html import generate_verify_html

    config = load_app_config(repo_root)
    generate_verify_html(
        results, results_dir / "report.html",
        results_dir=results_dir,
        app_name=config.name,
        wall_ms=wall_ms,
    )

    passed = sum(1 for r in results.values() if r.success)
    failed = len(results) - passed

    for scenario_path, result in results.items():
        status = "PASSED" if result.success else "FAILED"
        click.echo(f"  {status}: {scenario_path} ({result.duration_ms}ms)")
        for err in result.errors:
            click.echo(f"    {err}", err=True)

    click.echo(f"\n{passed} passed, {failed} failed")
    click.echo(f"Report: {results_dir / 'report.html'}")
    if failed > 0:
        raise SystemExit(1)



@main.command()
@click.option("--app", default=None, help="Filter by app name.")
@click.option("--scenario", default=None, help="Filter by scenario path.")
@click.option("--web-version", default=None, help="Filter by web version.")
@click.option("--api-version", default=None, help="Filter by API version.")
@click.option("--env", "env_name", default=None, help="Filter by environment name.")
def runs(
    app: str | None,
    scenario: str | None,
    web_version: str | None,
    api_version: str | None,
    env_name: str | None,
) -> None:
    """List recorded test runs."""
    from scout.index import IndexDB

    index_path = Path.cwd() / ".scout" / "index.db"
    if not index_path.exists():
        click.echo("No runs found.")
        return

    db = IndexDB(index_path)
    rows = db.query(app=app, scenario=scenario, web_version=web_version,
                    api_version=api_version, env=env_name)
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
@click.option("--detail/--no-detail", default=True, help="Include raw request/response data in diff (default: enabled, needed for popup body display).")
def diff(baseline: str, target: str, detail: bool) -> None:
    """Compare API recordings between two runs."""
    from urllib.parse import urlparse

    from scout.collector.db import RecordingDB
    from scout.config import load_app_config
    from scout.matcher.align import align_records
    from scout.matcher.compare import compare_pair
    from scout.matcher.diff_db import DiffDB
    from scout.matcher.diff_report import generate_diff_html
    from scout.matcher.normalize import extract_dynamic_pairs, extract_query_dynamic_pairs

    repo_root = Path.cwd()
    scout_dir = repo_root / ".scout"

    # Load diff_ignore from diff_ignore.json (separate from app.json)
    from scout.config import load_diff_ignore_config
    diff_ignore_cfg = load_diff_ignore_config(repo_root)

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

    # Read all sessions and index by scenario
    base_sessions = {dict(s)["scenario"]: dict(s) for s in base_rdb.get_all_sessions()}
    target_sessions = {dict(s)["scenario"]: dict(s) for s in target_rdb.get_all_sessions()}

    if not base_sessions or not target_sessions:
        click.echo("Error: no recording sessions found in one or both runs.", err=True)
        raise SystemExit(1)

    # Determine app name and versions from first session
    base_first = next(iter(base_sessions.values()))
    target_first = next(iter(target_sessions.values()))
    app_name = base_first.get("app", "")
    baseline_ver = base_first.get("web_version") or base_first.get("app_version") or ""
    target_ver = target_first.get("web_version") or target_first.get("app_version") or ""

    # Compare + write results
    diff_dir = scout_dir / "diffs" / f"{baseline}_vs_{target}"
    ddb = DiffDB(diff_dir / "diff.db")
    ddb.set_meta(
        baseline_run_id=baseline,
        target_run_id=target,
        app=app_name,
        baseline_version=baseline_ver,
        target_version=target_ver,
    )

    def _always_kwargs(rec: dict, prefix: str) -> dict:
        """Small fields that are always stored regardless of --detail.
        Duration enables latency-delta sorting in the report; it's just an int.
        """
        return {
            f"{prefix}_duration": rec.get("duration_ms"),
        }

    def _detail_kwargs(rec: dict, prefix: str) -> dict:
        """Heavy fields only stored when --detail (bodies, headers, full URLs)."""
        if not detail:
            return {}
        return {
            f"{prefix}_url": rec.get("url"),
            f"{prefix}_request": rec.get("request_body"),
            f"{prefix}_response": rec.get("response_body"),
            f"{prefix}_request_headers": rec.get("request_headers"),
            f"{prefix}_response_headers": rec.get("response_headers"),
            f"{prefix}_timestamp": rec.get("timestamp"),
        }

    def _normalize_dynamic_ids(
        rec: dict, dyn_pairs: list[tuple[str, str]], side: str,
    ) -> dict:
        """Substitute dynamic path segments in request/response bodies with stable
        placeholders, so paired records that differ only by path-derived IDs compare
        as equal. Returns a shallow copy; original record is untouched.

        Each (baseline_seg, target_seg) pair gets its own indexed placeholder, so
        multiple dynamic segments in the same path don't collide.
        """
        if not dyn_pairs:
            return rec
        out = dict(rec)
        for body_key in ("request_body", "response_body"):
            body = out.get(body_key)
            if not isinstance(body, str):
                continue
            for i, (a, b) in enumerate(dyn_pairs):
                value = a if side == "baseline" else b
                if not value:
                    continue
                body = body.replace(value, f"__SCOUT_DYN_{i}__")
            out[body_key] = body
        return out

    def _build_step_labels(rdb: RecordingDB, session_id: int) -> dict[int, str]:
        """Build seq → label mapping from steps table."""
        labels: dict[int, str] = {}
        for s in rdb.get_steps(session_id):
            action = s.get("action", "")
            name = s.get("element_name") or s.get("page_url") or ""
            labels[s["seq"]] = f"{action} {name}".strip()
        return labels

    def _build_offset_map(rdb: RecordingDB, session_id: int) -> dict[int, int]:
        """Build record_id → offset_ms from scenario's first record."""
        from datetime import datetime as _dt, timezone as _tz
        records = rdb.get_api_records(session_id)
        if not records:
            return {}
        # Parse all timestamps, find earliest
        def _parse(ts: str) -> _dt:
            return _dt.fromisoformat(ts)
        t0 = _parse(records[0]["timestamp"])
        return {
            r["id"]: int((_parse(r["timestamp"]) - t0).total_seconds() * 1000)
            for r in records
        }

    # Process each scenario present in either run
    all_scenarios = sorted(set(base_sessions) | set(target_sessions))
    for scenario_name in all_scenarios:
        base_s = base_sessions.get(scenario_name)
        target_s = target_sessions.get(scenario_name)

        if base_s and target_s:
            base_records = base_rdb.get_api_records(base_s["id"])
            target_records = target_rdb.get_api_records(target_s["id"])
            # Build step labels from baseline (both runs share the same steps)
            step_labels = _build_step_labels(base_rdb, base_s["id"])
            if not step_labels:
                step_labels = _build_step_labels(target_rdb, target_s["id"])
            base_offsets = _build_offset_map(base_rdb, base_s["id"])
            target_offsets = _build_offset_map(target_rdb, target_s["id"])
            aligned = align_records(base_records, target_records)

            for pair in aligned:
                if pair.baseline is not None and pair.target is not None:
                    # Use baseline step_seq (or target if baseline is None)
                    step_seq = pair.baseline.get("step_seq") or pair.target.get("step_seq")
                    step_label = step_labels.get(step_seq) if step_seq else None

                    # status_only: skip structure/value diff for matching rules
                    if diff_ignore_cfg.is_status_only(scenario_name, pair.method, pair.path, step_seq):
                        b_status = pair.baseline.get("status_code")
                        t_status = pair.target.get("status_code")
                        result_status_match = b_status == t_status
                        b_id = pair.baseline.get("id")
                        t_id = pair.target.get("id")
                        ddb.insert_endpoint_diff(
                            scenario=scenario_name,
                            baseline_record_id=b_id,
                            target_record_id=t_id,
                            method=pair.method,
                            path=pair.path,
                            step_seq=step_seq,
                            step_label=step_label,
                            baseline_offset_ms=base_offsets.get(b_id) if b_id else None,
                            target_offset_ms=target_offsets.get(t_id) if t_id else None,
                            status_match=result_status_match,
                            baseline_status=b_status,
                            target_status=t_status,
                            structure_match=True,
                            diff_summary="",
                            value_match=True,
                            value_diff="",
                            **_always_kwargs(pair.baseline, "baseline"),
                            **_always_kwargs(pair.target, "target"),
                            **_detail_kwargs(pair.baseline, "baseline"),
                            **_detail_kwargs(pair.target, "target"),
                        )
                        continue

                    ignore_rule = diff_ignore_cfg.rule_for(pair.method, pair.path)
                    # Replace dynamic URL components with stable placeholders before
                    # comparing — eliminates noise from per-run-unique IDs leaking
                    # from the URL into request/response bodies. We extract from
                    # both path segments (e.g. /orders/ord_A vs /orders/ord_B) and
                    # query values (e.g. ?q=test-1a64e3 vs ?q=test-726260). Pairs
                    # are detected by *comparing the two records*, not by guessing
                    # from value shape — alignment already grouped these together
                    # on path + query key set, so any value differences within a
                    # pair are by definition the dynamic parts.
                    b_parsed = urlparse(pair.baseline.get("url") or "")
                    t_parsed = urlparse(pair.target.get("url") or "")
                    dyn_pairs = (
                        extract_dynamic_pairs(b_parsed.path, t_parsed.path)
                        + extract_query_dynamic_pairs(b_parsed.query, t_parsed.query)
                    )
                    baseline_for_compare = _normalize_dynamic_ids(pair.baseline, dyn_pairs, "baseline")
                    target_for_compare = _normalize_dynamic_ids(pair.target, dyn_pairs, "target")
                    result = compare_pair(
                        baseline_for_compare, target_for_compare,
                        ignore=ignore_rule,
                        known_changes=diff_ignore_cfg.known_changes,
                        target_version=target_ver,
                        api_path=pair.path,
                        header_ignore=diff_ignore_cfg.header_ignore,
                    )
                    b_id = pair.baseline.get("id")
                    t_id = pair.target.get("id")
                    ddb.insert_endpoint_diff(
                        scenario=scenario_name,
                        baseline_record_id=b_id,
                        target_record_id=t_id,
                        method=pair.method,
                        path=pair.path,
                        step_seq=step_seq,
                        step_label=step_label,
                        baseline_offset_ms=base_offsets.get(b_id) if b_id else None,
                        target_offset_ms=target_offsets.get(t_id) if t_id else None,
                        status_match=result.status_match,
                        baseline_status=result.baseline_status,
                        target_status=result.target_status,
                        structure_match=result.structure_match,
                        diff_summary=result.diff_summary,
                        value_match=result.value_match,
                        value_diff=result.value_diff,
                        header_match=result.header_match,
                        header_diff=result.header_diff,
                        **_always_kwargs(pair.baseline, "baseline"),
                        **_always_kwargs(pair.target, "target"),
                        **_detail_kwargs(pair.baseline, "baseline"),
                        **_detail_kwargs(pair.target, "target"),
                    )
                elif pair.baseline is not None:
                    # Endpoint present only in baseline — insert into the unified
                    # endpoint_diffs table with target side NULL. status_match etc.
                    # are True (nothing to compare), and the "missing" classification
                    # is derived from target_record_id IS NULL.
                    b_id = pair.baseline.get("id")
                    step_seq = pair.baseline.get("step_seq")
                    step_label = step_labels.get(step_seq) if step_seq else None
                    ddb.insert_endpoint_diff(
                        scenario=scenario_name,
                        baseline_record_id=b_id,
                        target_record_id=None,
                        method=pair.method,
                        path=pair.path,
                        step_seq=step_seq,
                        step_label=step_label,
                        baseline_offset_ms=base_offsets.get(b_id) if b_id else None,
                        target_offset_ms=None,
                        status_match=True,
                        baseline_status=pair.baseline.get("status_code"),
                        target_status=None,
                        structure_match=True,
                        diff_summary="",
                        value_match=True,
                        value_diff="",
                        **_always_kwargs(pair.baseline, "baseline"),
                        **_detail_kwargs(pair.baseline, "baseline"),
                    )
                elif pair.target is not None:
                    t_id = pair.target.get("id")
                    step_seq = pair.target.get("step_seq")
                    step_label = step_labels.get(step_seq) if step_seq else None
                    ddb.insert_endpoint_diff(
                        scenario=scenario_name,
                        baseline_record_id=None,
                        target_record_id=t_id,
                        method=pair.method,
                        path=pair.path,
                        step_seq=step_seq,
                        step_label=step_label,
                        baseline_offset_ms=None,
                        target_offset_ms=target_offsets.get(t_id) if t_id else None,
                        status_match=True,
                        baseline_status=None,
                        target_status=pair.target.get("status_code"),
                        structure_match=True,
                        diff_summary="",
                        value_match=True,
                        value_diff="",
                        **_always_kwargs(pair.target, "target"),
                        **_detail_kwargs(pair.target, "target"),
                    )
        elif base_s:
            # Scenario only in baseline — every endpoint becomes a baseline-only row
            from scout.matcher.normalize import normalize_url
            for rec in base_rdb.get_api_records(base_s["id"]):
                b_id = rec.get("id")
                ddb.insert_endpoint_diff(
                    scenario=scenario_name,
                    baseline_record_id=b_id,
                    target_record_id=None,
                    method=rec["method"],
                    path=normalize_url(rec["url"]),
                    step_seq=rec.get("step_seq"),
                    step_label=None,
                    baseline_offset_ms=None,
                    target_offset_ms=None,
                    status_match=True,
                    baseline_status=rec.get("status_code"),
                    target_status=None,
                    structure_match=True,
                    diff_summary="",
                    value_match=True,
                    value_diff="",
                    **_always_kwargs(rec, "baseline"),
                    **_detail_kwargs(rec, "baseline"),
                )
        else:
            # Scenario only in target — every endpoint becomes a target-only row
            from scout.matcher.normalize import normalize_url
            for rec in target_rdb.get_api_records(target_s["id"]):
                t_id = rec.get("id")
                ddb.insert_endpoint_diff(
                    scenario=scenario_name,
                    baseline_record_id=None,
                    target_record_id=t_id,
                    method=rec["method"],
                    path=normalize_url(rec["url"]),
                    step_seq=rec.get("step_seq"),
                    step_label=None,
                    baseline_offset_ms=None,
                    target_offset_ms=None,
                    status_match=True,
                    baseline_status=None,
                    target_status=rec.get("status_code"),
                    structure_match=True,
                    diff_summary="",
                    value_match=True,
                    value_diff="",
                    **_always_kwargs(rec, "target"),
                    **_detail_kwargs(rec, "target"),
                )

    base_rdb.close()
    target_rdb.close()

    # Generate report
    meta = ddb.get_meta()
    diffs = ddb.get_endpoint_diffs()
    summary = ddb.summary()
    ddb.close()

    # Read raw diff_ignore.json for embedding in report
    import json as _json
    di_path = repo_root / "diff_ignore.json"
    di_raw = _json.loads(di_path.read_text(encoding="utf-8")) if di_path.exists() else {}
    generate_diff_html(meta, diffs, summary, diff_dir / "report.html",
                       diff_ignore=di_raw, repo_root=repo_root)

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

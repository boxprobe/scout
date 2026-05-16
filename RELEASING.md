# Releasing scout

Releases are published to PyPI via GitHub Actions Trusted Publishing
(OIDC). No long-lived API tokens are stored as repository secrets.

## One-time setup

These steps must be done once, by a maintainer, before the first release.

### 1. Register the PyPI trusted publisher

On [pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/)
add a **pending publisher** with:

| Field | Value |
|---|---|
| PyPI Project Name | `boxprobe-scout` |
| Owner | `boxprobe` |
| Repository name | `scout` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

This registers the publisher *before* the project exists on PyPI. The
first successful release creates the project page and binds it to this
publisher.

### 2. Create the `pypi` GitHub Environment

Repo settings → Environments → New environment → name it `pypi`.

Recommended protection: require manual approval from a maintainer before
the publish job runs. This is the last guard against an accidental tag
push triggering an unintended release.

## Cutting a release

1. **Update `CHANGELOG.md`** — move items from `[Unreleased]` into a new
   `[X.Y.Z] - YYYY-MM-DD` section, and update the link references at the
   bottom of the file.

2. **Bump the version** in `pyproject.toml`:
   ```toml
   version = "X.Y.Z"
   ```

3. **Verify locally**:
   ```bash
   uv run ruff check scout/ tests/
   uv run pyright scout/
   uv run pytest tests/ -m "not e2e"
   uv build
   ```

4. **Commit and push**:
   ```bash
   git commit -am "chore: release vX.Y.Z"
   git push
   ```

5. **Tag the release commit and push the tag**:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

6. **Approve in GitHub Environments** (if the `pypi` environment requires
   reviewers). The workflow waits at the publish step until approved.

7. After the workflow completes:
   - `pip install boxprobe-scout==X.Y.Z` resolves on PyPI
   - A GitHub Release with the changelog excerpt is created automatically
   - sdist + wheel are attached to the release

## Hotfix flow

For an urgent patch:

1. Branch from the existing release tag: `git checkout -b hotfix/X.Y.Z vX.Y.(Z-1)`
2. Apply the fix; commit; bump to `X.Y.Z`
3. Open a PR; review and merge
4. Tag and push as usual

## Versioning rules (pre-1.0)

- **Patch** (`0.1.3 → 0.1.4`): bug fixes, internal refactors, doc updates.
  No CLI or DSL surface changes. No new dependencies.
- **Minor** (`0.1.x → 0.2.0`): new features, CLI surface additions, may
  include breaking changes to internal APIs. The scenario file format and
  diff report HTML are considered stable from `0.2.0` onward.
- **Major** (`0.x → 1.0.0`): only when scenario file format, CLI surface,
  and diff report HTML are stable enough to commit to semver.

## Manual TestPyPI dry-run (optional)

To validate a release without going to real PyPI first:

```bash
uv build
uv publish --publish-url https://test.pypi.org/legacy/ \
    --username __token__ --password "$TESTPYPI_TOKEN" dist/*
```

You need a TestPyPI account and an API token (TestPyPI uses traditional
tokens; trusted publishing setup is the same shape but on the test domain
if you want to wire it up).

Then install from TestPyPI to verify:

```bash
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    boxprobe-scout==X.Y.Z
```

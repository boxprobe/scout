# Agent Constraints

1. **Run tests before committing**: `uv run pytest tests/ -x --tb=short`
2. **Don't touch unrelated code** — scope changes to the task at hand
3. **Conventional commits** — `feat:`, `fix:`, `test:`, `refactor:`, `docs:`
4. **Don't add dependencies** without explicit approval
5. **All Python commands via `uv run`** — never bare `python` or `pip`

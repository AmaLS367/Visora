# 🤝 Contributing to Visora

> Thank you for helping make Unity workflows safer and more useful for agents.

Visora provides typed, safety-conscious MCP tools for Unity Editor workflows. Every change should be easy for both an agent and a maintainer to understand, verify, and safely ship.

---

## 🧭 Before opening an issue

Read the [setup guide](docs/SETUP_GUIDE.md) and [agent workflow guide](docs/AGENT_WORKFLOWS.md). For a defect, use the bug-report form and include a minimal, reproducible Unity bridge setup. Never include credentials, private Unity assets, or proprietary scene data.

> 🔐 For security vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of filing a public issue.

---

## 🛠️ Development setup

```bash
uv sync --locked --all-extras
```

Run the full validation gate before opening a pull request:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy .
uv run pytest
```

Use `uv` for all Python commands. Changes that affect Unity behavior should be verified against a live bridge when practical; report bridge failures clearly rather than masking them.

---

## 🔍 Pull requests

- Keep each pull request focused and use a conventional-commit title.
- Prefer typed Pydantic models at tool boundaries and compact agent-friendly outputs.
- Update all callers, imports, and tests when refactoring. Do not add internal backward-compatibility aliases or shims.
- Preserve Unity scene safety: do not save during Play Mode, restore temporary state, and make destructive operations explicit.
- Update documentation, schemas, and tests whenever user-facing behavior changes.

---

## ⚖️ Contribution license

By submitting a contribution, you agree to license it under the [Apache License 2.0](LICENSE).

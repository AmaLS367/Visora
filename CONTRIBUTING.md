# 🤝 Contributing to Visora

> Thank you for helping make Unity workflows safer, more predictable, and more capable for AI agents.

Visora provides typed, safety-conscious MCP tools for Unity Editor workflows. Every change should be easy for both an agent and a human maintainer to understand, verify, and safely ship.

---

## 🧭 Before Opening an Issue

Before creating a new issue, please consult the relevant documentation:
- 📖 [Documentation Index](docs/README.md)
- 🛠️ [Setup Guide](docs/SETUP_GUIDE.md)
- 🤖 [Agent Workflow Guide](docs/AGENT_WORKFLOWS.md)
- 🏗️ [Backend Development Guide](docs/backend/DEVELOPMENT.md)

> [!NOTE]
> When reporting a defect, please provide minimal, reproducible Unity bridge reproduction steps. Never include credentials, API tokens, private Unity assets, or proprietary scene data.

> [!IMPORTANT]
> 🔐 **Security Vulnerabilities**: For security-sensitive issues, follow [SECURITY.md](SECURITY.md) privately rather than opening a public issue.

---

## 🛠️ Development Setup

Install dependencies and set up the local environment:

```bash
uv sync --locked --all-extras
```

### 🧪 Full Validation Gate

Before submitting a pull request, run the complete validation suite:

```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy .
uv run pytest
```

### 🎮 Unity Package Validation Gate

When making changes under `unity-package/`, run the C# compile and format checks. Animation-stack changes also require the Unity EditMode integration gate:

```bash
uv run python scripts/check_unity_package.py
uv run python scripts/check_unity_package.py --format
uv run python scripts/check_unity_tests.py
```

> [!TIP]
> **Change-Based Validation**: Documentation-only and non-functional edits do not require running the full test suite. Read the detailed policy in [Backend Development](docs/backend/DEVELOPMENT.md#validation-by-change-type).

---

## 🔍 Pull Request Checklist

When submitting a pull request, please ensure:

- [ ] 🎯 **Focused Scope**: Keep changes focused with a clean conventional commit title (e.g. `feat(vision): ...`, `fix(bridge): ...`).
- [ ] 📐 **Typed Contracts**: Use typed Pydantic models at tool boundaries with compact, agent-friendly responses.
- [ ] 🚫 **No Internal Backwards Compatibility**: When refactoring, update all callers and tests directly. Never introduce internal Python compatibility shims.
- [ ] 🛡️ **Preserve Scene Safety**: Never auto-save during Play Mode, cleanly restore temporary state, and make destructive actions explicit.
- [ ] 📚 **Keep Docs in Sync**: Update documentation, schemas, and tests whenever user-facing behavior or parameters change.

---

## ⚖️ License

By submitting a contribution, you agree to license your work under the [Apache License, Version 2.0](LICENSE).


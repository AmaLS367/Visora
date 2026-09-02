# Agent Guidelines & Workflow

> [!IMPORTANT]
> All guidelines, rules, and workflows for AI agents in this repository have been centralized in **[AGENTS.md](AGENTS.md)**.
>
> You **MUST** refer to and follow the instructions in **[AGENTS.md](AGENTS.md)** before utilizing any tools, exploring code, or initiating reviews.

## ⚠️ CRITICAL INSTRUCTION FOR ALL AI AGENTS

* **Never. NEVER IN YOUR LIFE TRY TO RUSH AND DO EVERYTHING QUICKLY. ALWAYS DO EXACTLY WHAT THE USER WANTS.**
* **When the user asks questions, discusses ideas, or points something out: ONLY answer the question and discuss. NEVER make unprompted file edits, rename files, or run mutating actions unless the user explicitly commands you to execute them.**
* **Strictly NO internal backward compatibility in Python:** Zero tolerance for backward compatibility layers, legacy aliases, compatibility wrappers, or preserving deprecated identifiers/imports inside the Python codebase. The ONLY backward compatibility allowed anywhere in this project is the external HTTP/JSON transport protocol with Unity Editor's AnkleBreaker bridge. When code, modules, functions, or signatures change, all callers, imports, and tests MUST be updated directly to the new canonical interface. Never introduce compatibility shims.
* **Always meticulously verify syntax (brackets, quotes, comments, tags, e.g. HTML `<!-- -->` tags, and indentation) after every single edit to ensure absolutely no syntax errors or unclosed elements are introduced.**

# Architecture Decision Records (ADRs)

Decisions that shape `aeo-npui`. Each ADR captures a load-bearing choice —
the kind that another agent or contributor should not silently reverse.

## Format

Each file is named `ADR-###-short-slug.md` and opens with frontmatter:

```
---
Title: <short decision title>
Status: Proposed | Accepted | Superseded by ADR-### | Deprecated
Date: YYYY-MM-DD
---
```

Body sections (in order):

1. **Context** — the force or constraint that made a decision necessary.
2. **Decision** — the choice in one or two sentences.
3. **Consequences** — what becomes easier, what becomes harder, and what
   new work follows from the decision.
4. **Alternatives Considered** — the paths not taken, and why.
5. **Status** — typically mirrors the frontmatter; if superseded, link
   to the replacing ADR.

Target length: 40–200 lines. If an ADR needs more, extract the detail
into a reference doc under `../references/` and link from the ADR.

## Numbering

ADRs are numbered in order of acceptance. Numbers are stable once
issued; a superseded ADR keeps its number and its `Status:` line is
updated.

## Current ADRs

| ID | Title | Status |
|---|---|---|
| 001 | Rich + Typer TUI demoted | Accepted |
| 002 | UI is Layer-1 client only | Accepted |
| 003 | Identical UX across launch origin | Accepted |
| 004 | Native shell is Tauri 2 | Accepted |
| 005 | Frontend toolchain = Bun + Vite | Accepted |
| 006 | Auto-updater via GitHub Releases | Accepted |
| 007 | Signing = SignPath Foundation OSS | Accepted |
| 008 | Service API = HTTP + SSE (FastAPI) | Accepted |
| 009 | Layer 0 runtime = custom Python + OpenVINO | Accepted |
| 010 | Storage = %LOCALAPPDATA%\AeyeOps, API-mediated | Accepted |
| 011 | Python 3.13 workspace pin | Accepted |

Reserved: ADR-012 (tauri-driver choice, Iteration 3.5), ADR-013
(styling choice, Iteration 3.3).

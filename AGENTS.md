# AGENTS.md

Automation conventions for the `aeo-npui` monorepo. Audience: general
agents and shell-level workflows. For Claude Code-specific guidance see
[`CLAUDE.md`](./CLAUDE.md).

## Package managers (one per layer)

| Layer | Tool | Where |
|---|---|---|
| Layer 1 — Python service | `uv` | `service/` |
| Layer 3 — Desktop frontend | `bun` | `desktop/` (Iteration 2+) |
| Layer 3 — Tauri shell (Rust) | `cargo` | `desktop/src-tauri/` (Iteration 2+) |
| System (OS-native libs) | `apt` / `brew` / `winget` | [`bootstrap/`](./bootstrap/) |

Never introduce a parallel package manager in a layer that already has
one. No `npm`/`yarn`/`pnpm` in `desktop/`; no `poetry`/`pip` in
`service/`. The `npm`/`yarn`/`pnpm` side is enforced by `make no-npm`,
which fails if a `package-lock.json` appears at repo root, `desktop/`,
or `service/`. The Python side is convention-enforced via review.

System-level prerequisites (things the language-level managers can't
install — `libwebkit2gtk-4.1`, MSVC Build Tools, etc.) are declared in
`bootstrap/<os>.txt` and installed via `make bootstrap` on Linux/macOS
or `bootstrap/bootstrap.ps1` on Windows. See
[`bootstrap/README.md`](./bootstrap/README.md) for the pattern.

## Versioning — declare loose, lock tight

Manifests use `>=` (minimum-tested-version) constraints; the lock file
pins. CI installs with `uv sync --frozen`, `bun install --frozen-lockfile`,
and `cargo build --locked`. A PR that changes a manifest without updating
the lock file fails CI before review.

## Windows shell preference

When invoking PowerShell from WSL, prefer `pwsh.exe` over
`powershell.exe`. Do not route scripts through `cmd.exe` except for the
documented `cmd.exe /c start "" "<path>"` pattern used to launch the
installed Tauri binary from WSL.

## Windows Python environment

When a Windows-side Python environment is needed for NPU execution, use:

```powershell
conda activate npu
```

The `npu` conda environment is the Windows runtime for Layer 0 (OpenVINO
on NPU). The WSL-side `uv` venv runs dev/test surfaces only.

## Layer boundaries — what each layer may NOT do

- **Layer 3 (desktop/)** may not invoke `pwsh.exe`, touch the filesystem
  directly for NPU data, or call Tauri `invoke()` for NPU concerns. UI
  talks only to Layer 1 via HTTP + SSE at `127.0.0.1:<service-port>`.
- **Layer 2 (service/src/npu_service/launcher/)** owns all cross-OS
  orchestration (WSL↔Windows bridge, conda activation, probe dispatch).
- **Layer 1 (service/)** wraps Layer 0; exposes a stable HTTP+SSE
  contract documented in `docs/contracts/service-api.md`.
- **Layer 0 (OpenVINO on NPU)** is invoked only from Layer 1's worker.

Violations are P0 defects. The UI reaching for shell escapes is the
classic regression; CI and ADR-002 both guard against it.

## Monorepo layout (summary)

```
aeo-npui/
├── service/     Layer 1 Python — FastAPI + SSE, OpenVINO worker, launcher
├── desktop/     Layer 3 Tauri 2 — React + Vite UI, Rust shell (Iteration 2+)
├── docs/        intent, architecture, ADRs, contracts, roadmap, archive
└── scripts/     repo-level dev helpers (bash)
```

See `docs/architecture.md` for the full layer model and responsibilities.

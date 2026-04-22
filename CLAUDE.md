# CLAUDE.md

Claude Code-specific guidance for this repo. Audience: the Claude Code
assistant. For general automation conventions see
[`AGENTS.md`](./AGENTS.md). For the architecture itself see
[`docs/architecture.md`](./docs/architecture.md).

## Command cheat-sheet

First-time setup — install OS-native system prerequisites (webkit2gtk,
MSVC Build Tools, WebView2, …) declared in `bootstrap/<os>.txt`:

```bash
make bootstrap                   # Linux / WSL / macOS
.\bootstrap\bootstrap.ps1        # Windows (PowerShell)
```

`make ci` assumes these are installed. If `cargo build --locked` errors
out on `pkg-config` or a missing linker, run `make bootstrap` first.
See [`bootstrap/README.md`](./bootstrap/README.md) for the pattern.

Service (Layer 1, Python):

```bash
cd service
uv run ruff check               # lint
uv run ty check                 # type-check (Astral; see Type-checking rule)
uv run pytest                   # tests
uv run npu-service serve        # start FastAPI + SSE on 127.0.0.1:8765
```

Desktop (Layer 3, Tauri 2 — Iteration 2+):

```bash
cd desktop
bun run tauri dev               # dev loop (native window + Vite HMR)
bun run tauri build             # produce MSI + NSIS in src-tauri/target/release/bundle/
bun run typecheck               # tsc (the only TypeScript type checker)
bun run test:e2e                # Playwright via tauri-driver (Iteration 3+)
```

Repo-level:

```bash
make ci                         # service + desktop (Linux cargo) + (on WSL) Windows NSIS/MSI bundles + locks + guards
make build-windows              # NSIS+MSI only; syncs repo to %TEMP%\aeo-npui-build and runs tauri build in the VS Dev shell
make bootstrap                  # one-time setup; also mirrors the Tauri updater key WSL→Windows when on WSL
scripts/launch-dev.sh           # service + tauri dev in parallel
scripts/winlaunch.sh <winpath>  # WSL-origin launch of an installed Windows app (cd's into %TEMP% first — avoids the cmd.exe UNC-CWD trap)
scripts/gen-types.sh [--check]  # Pydantic → TS codegen (Iteration 4+)
```

On WSL, `make ci` produces both the Linux `cargo build --locked` gate
and the Windows `bun run tauri build` bundles in a single process —
no need to alternate hosts. Override the Windows-side staging dir with
`WIN_BUILD_DIR='C:\dev\aeo-npui' make build-windows` (defaults to
`%TEMP%\aeo-npui-build`).

## Type-checking rule (the only type checker is `ty`)

Python: `ty` (Astral). Declared in `service/pyproject.toml` dev-group;
configured with `python-version = "3.13"` and `error-on-warning = true`.
Never install or invoke `mypy`, `pyright`, `pytype`, or `pylance`. Editors
that default to pyright should have that extension disabled. If `ty`
lacks coverage for a given construct, add a scoped suppression and file
an upstream issue — do not reach for a second checker.

TypeScript: `tsc` via `bun run typecheck`. No alternate JS/TS checker.

Both rules are enforced by `make checker-purity` (see the repo
`Makefile`).

## Versioning rule

Manifests use `>=` constraints; lock files are the source of truth for
installed versions and are committed. CI installs with:

- `uv sync --frozen`
- `bun install --frozen-lockfile`
- `cargo build --locked` (desktop/src-tauri/, Iteration 2+)

Before writing a version to a manifest, verify it is published. For
`uses:` lines in GitHub Actions workflows, pin the floating major
(e.g. `actions/checkout@v4`) and check the major is still maintained.

## Python version pin

The workspace pins `>=3.13,<3.14`. This departs from the user's
default `3.12.3`; the rationale lives in ADR-011
([`docs/decisions/ADR-011-python-3-13-workspace-pin.md`](./docs/decisions/ADR-011-python-3-13-workspace-pin.md)).
If a future workspace member cannot tolerate 3.13, revisit ADR-011 rather
than silently pinning a second Python version.

## Layer boundaries — examples of forbidden calls

If you are editing `desktop/src/**` and reach for any of the following,
stop and route the call through Layer 1 instead:

- Tauri `invoke()` that does NPU operations → put behind a REST call to
  `POST /inference` or similar (see `docs/contracts/service-api.md`).
- Tauri `shell.open()` or `shell.execute()` for `pwsh.exe`/`conda` → this
  belongs in `service/src/npu_service/launcher/`.
- Direct filesystem reads of `%LOCALAPPDATA%\AeyeOps\aeo-npui\` → the
  service mediates storage; desktop asks the service (ADR-010).

## Test expectations

- Service: `uv run pytest` in `service/`. Lint, type-check, and tests
  are bundled into `make service` (see the repo `Makefile`).
- Desktop E2E: Playwright driven via `tauri-driver` against the built
  Tauri binary. Not against an Expo URL. Each scenario runs twice (once
  launched from Windows `pwsh.exe`, once from WSL via `cmd.exe /c start`)
  — cross-launch parity is an invariant.

## Version sources of truth

| Component | File |
|---|---|
| Python service | `service/pyproject.toml` |
| Desktop frontend | `desktop/package.json` (Iteration 2+) |
| Tauri shell | `desktop/src-tauri/Cargo.toml` (Iteration 2+) |

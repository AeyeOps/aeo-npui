# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The canonical version lives in [`VERSION`](./VERSION) at the repo root;
every per-language manifest (`package.json`, `Cargo.toml`, `pyproject.toml`,
`tauri.conf.json`) is kept in sync via `scripts/version.py` and guarded by
`make version-check`.

## [0.1.0] — 2026-04-22

First tagged slice. Iterations 1 and 2 of the `reflective-toasting-crescent`
plan land in a single initial release: the Layer-1 Python service is
extracted from `AeyeOps/aeo-infra/npu/` and cleared of all CI gates; the
Layer-3 Tauri 2 desktop shell is scaffolded, wired to the service over
`127.0.0.1:8765`, and produces signed NSIS + MSI installers on Windows.

### Added

- **Service (Layer 1)** — `npu-service` Python package exposing a FastAPI
  app on `127.0.0.1:8765` with a `/health` probe endpoint, SSE event
  stream contract, and OpenVINO NPU worker scaffolding. Extracted from
  `aeo-infra/npu/` with Git history preserved.
- **Desktop (Layer 3)** — Tauri 2 shell (Bun + Vite + React 19 +
  TypeScript) with an updater plugin pre-wired against a minisign keypair,
  a locked-down capabilities manifest, and a CSP that only permits traffic
  to `127.0.0.1:8765`. Produces `nsis` + `msi` bundles; bundles are
  signed for the auto-updater.
- **Bootstrap pattern** — `bootstrap/{apt,brew,winget}.txt` declare
  OS-level prerequisites; `bootstrap/bootstrap.{sh,ps1}` install them
  idempotently. On WSL, `bootstrap.sh` installs the Linux half via `apt`
  and delegates the Windows half to `pwsh.exe bootstrap.ps1` in a single
  call; it also mirrors the Tauri updater private key from
  `~/.tauri/aeo-npui.key` to `%USERPROFILE%\.tauri\aeo-npui.key`.
- **Unified CI** — `make ci` gates `service` (ruff + ty + pytest) +
  `desktop` (Linux cargo `--locked`) + (on WSL) `build-windows` (NSIS +
  MSI bundles in the VS Developer Shell) + lockfile integrity + no-npm
  guard + `ty`-only checker purity + `version-check`. No GitHub Actions —
  CI is the Makefile.
- **Windows build plumbing** — `scripts/make-windows.sh` stages the repo
  from WSL into a Windows-local directory (`%TEMP%\aeo-npui-build` or
  `$WIN_BUILD_DIR`) via rsync, then invokes `scripts/build-windows.ps1`
  inside the VS Developer Shell. Signing env vars
  (`TAURI_SIGNING_PRIVATE_KEY`, `..._PASSWORD`) are exported explicitly
  to prevent the known tauri-signer stdin hang.
- **WSL-origin launch helper** — `scripts/winlaunch.sh` `cd`s into a
  Windows-local CWD inside `cmd.exe` before calling `start`, sidestepping
  the UNC-fallback trap where cmd.exe silently falls back to `C:\Windows`
  when invoked with a WSL 9P CWD.
- **Dev loop** — `scripts/launch-dev.sh` starts the service and
  `tauri dev` in parallel with coordinated SIGINT cleanup.
- **Docs** — `docs/intent.md` (north star + invariants), 11 ADRs under
  `docs/decisions/`, contracts under `docs/contracts/` (service-api,
  events, metrics, endurance), roadmap under `docs/roadmap/`, architecture
  overview, hardware profile, and a pre-feasibility probe snapshot.
- **Single-source versioning** — `VERSION` at repo root;
  `scripts/version.py {check,sync,bump X.Y.Z}`; enforced by
  `make version-check`.

### Changed

- **License → Apache-2.0.** Originally committed as MIT in Iteration 1.3;
  flipped to Apache-2.0 in 0.1.0 for the explicit patent-grant clause.
  SignPath Foundation OSS eligibility is preserved (see
  [ADR-007](./docs/decisions/ADR-007-signing-signpath-foundation.md)).

### Security / Privacy

- **History squash** — the repo's git history was squashed to a single
  root commit in 0.1.0 to scrub real developer-machine identifiers
  (Windows auto-hostname, hardware SKU) that had leaked into test
  fixtures and early feasibility docs. Fixtures and docs now use
  `DESKTOP-EXAMPLE1` / `Example Laptop 14` placeholders.
- Checker-purity gate bans `mypy`, `pyright`, `pytype`, `pyre-check`,
  and `pylance` from every manifest; `ty` is the sole Python type
  checker.

[0.1.0]: https://github.com/AeyeOps/aeo-npui/releases/tag/v0.1.0

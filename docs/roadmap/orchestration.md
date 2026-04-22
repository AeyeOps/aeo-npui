# Orchestration (Layer 2) — Cross-OS Launcher

**Scope:** The thin bridge that lets a single Windows binary
(`aeo-npui.exe`) behave identically regardless of launch origin, and
that guarantees Layer 1 is running before Layer 3 tries to talk to it.
Layer 2 is invisible to both Layer 3 (UI) and Layer 1 (service) — it
exists only to paper over cross-OS invocation quirks.

**Invariants:**

- Single installed Windows `.exe` is the product artifact (ADR-004).
- UX is identical across launch origins (ADR-003); cross-launch diffs
  are P0 defects.
- The UI never invokes `pwsh.exe` / `conda` / shell (ADR-002). Those
  calls, when needed, live in `service/src/npu_service/launcher/`.

## Installed-binary location

NSIS-scoped install (default, non-admin):

```
%LOCALAPPDATA%\Programs\aeo-npui\aeo-npui.exe
```

Per-machine install (if `scope = "perMachine"` is ever set): falls back
to `C:\Program Files\aeo-npui\aeo-npui.exe`. The `productName` and
`mainBinaryName` fields in `tauri.conf.json` are both `"aeo-npui"`
(lowercase, hyphenated) so the path is predictable and free of spaces.
Branding — `"AEO NPUi"` — lives only in the window title.

## Launch from Windows

```powershell
# Start menu → AEO NPUi
# or from pwsh:
& "$env:LOCALAPPDATA\Programs\aeo-npui\aeo-npui.exe"
```

## Launch from WSL (principle-#4 smoke test)

`cmd.exe` cannot consume POSIX paths and `$LOCALAPPDATA` is a Windows
env var (unset in WSL by default), so the path must come from
`cmd.exe` itself:

```bash
LOCALAPPDATA_WIN="$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')"
cmd.exe /c start "" "$LOCALAPPDATA_WIN\\Programs\\aeo-npui\\aeo-npui.exe"
```

The empty `""` after `start` is the window-title slot — required when
the path is quoted. Pattern is authoritative per plan **§2.5**. Running
the Tauri `.exe` straight out of the build tree
(`/opt/aeo/aeo-npui/desktop/src-tauri/target/release/...`) is measurably
slower (9P share) and must not be used for the parity test — use the
installed binary.

## Service autostart

1. On first UI paint, the Tauri shell performs
   `fetch("http://127.0.0.1:<port>/health")`.
2. If the fetch resolves 2xx within a short timeout, UI proceeds.
3. If the fetch fails with `ConnectionRefusedError` or equivalent:
   - **Option A (Tauri sidecar):** Tauri spawns the service as a
     sidecar process bundled into the installer (production path once
     Iteration 4.5 lands).
   - **Option B (Layer-2 launcher):** The shell invokes the
     `launcher/windows.py` entrypoint which runs
     `uv run npu-service serve --host 127.0.0.1 --port <port>` in the
     `npu` conda env on the Windows host.
4. UI re-polls `/health` with backoff until 2xx, then proceeds.
5. UI transitions to an error state if service fails to become
   ready within the deadline.

The implementation detail (sidecar vs Layer-2 launcher) lands in
Iteration 4.5. The contract — "UI pings `/health`, service is either up
or gets spawned" — is stable from Iteration 2 onward (Iteration 2 uses
a hand-started echo stub for the dev loop; see plan §2.3).

## Port reservation

- Default port: **8765**.
- Fail fast on port collision: if `127.0.0.1:8765` is already bound by
  something that isn't the npu service (no matching `/health`
  signature), the launcher aborts with a structured error rather than
  silently picking another port. Silent port-switching breaks the
  Tauri CSP (which pins `connect-src` to the specific port) and the
  cross-launch parity invariant.
- Dev-mode port override via `NPU_SERVICE_PORT` env var; honored by the
  service, the launcher, and the shell's dev config
  (`tauri.conf.dev.json`).

## WSL-originated commands (future — Iteration 4.5)

When an operator command originates in WSL but must be dispatched to
the Windows-side service:

- `launcher/wsl_bridge.py` translates POSIX paths to Windows paths
  (`wslpath -w`).
- Commands are serialized and forwarded to the service HTTP API; they
  do not cross into pwsh.exe from WSL directly.
- Any artifact path returned to WSL is re-translated
  (`wslpath -u`) so the bash caller can consume it.

## Cross-launch parity per ADR-003

Both origins (Windows-originated, WSL-originated) must produce:

- identical first-paint pixels,
- identical Tauri window chrome (decorations, title, icon),
- identical connection state in the service dot (green within the
  autostart deadline),
- identical working-directory behavior for the calling shell (WSL bash
  and Windows pwsh.exe stay put; the Tauri window owns its own session).

Any measurable divergence gets a bug filed before the iteration gate.

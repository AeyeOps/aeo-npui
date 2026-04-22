# `bootstrap/` — system-level prerequisites

Language-level package managers (`uv`, `bun`, `cargo`) declare and lock
library versions *inside* the project tree. They do **not** install the
native libraries those tools depend on — things like `libwebkit2gtk-4.1`
on Linux, Microsoft Visual C++ Build Tools on Windows, or Xcode CLT on
macOS. This directory fills that gap with a consistent cross-platform
pattern:

| Platform | Manifest | Installer | Driver |
|---|---|---|---|
| Debian/Ubuntu/WSL | [`apt.txt`](./apt.txt) | `apt-get` (via `sudo`) | [`bootstrap.sh`](./bootstrap.sh) |
| macOS | [`brew.txt`](./brew.txt) | `brew` | [`bootstrap.sh`](./bootstrap.sh) |
| Windows | [`winget.txt`](./winget.txt) | `winget` | [`bootstrap.ps1`](./bootstrap.ps1) |

Each manifest is a plain text file, one package per line. Blank lines
and `#` comments are ignored. **Edit the manifest, not the script** — the
dispatcher is deliberately boring.

## Usage

On Linux / macOS / **WSL** (single entry point):

```bash
make bootstrap
# equivalent to:  bash bootstrap/bootstrap.sh
```

On WSL, `bootstrap.sh` runs the Linux half (`sudo apt`) and then
delegates the Windows half to `bootstrap.ps1` via `pwsh.exe` (or
`powershell.exe` on first-ever run before pwsh is installed). Tauri
on Windows needs both halves wired, so WSL users get both in one call.
UAC or other must-have dialogs surface on the Windows desktop — those
are intended.

On **native Windows** (no WSL), call the PowerShell script directly:

```powershell
.\bootstrap\bootstrap.ps1
```

Both scripts are idempotent; re-running them reconciles any newly added
entries without disturbing already-installed packages.

## Why per-OS manifests instead of a single tool

System library coverage is asymmetric: `conda`/`pixi` has no WebView2 or
MSVC package for Windows, `brew` has no `apt`-style Windows target,
Nix's Windows support is WSL-only. Treating the three native package
managers (`apt`, `brew`, `winget`) as backends and keeping a thin
per-OS manifest is the simplest model that covers all three platforms
honestly without adding a new tool dependency.

This keeps the pattern in line with how the rest of the stack handles
prerequisites:

| Layer | Manifest | Lockfile | CI install command |
|---|---|---|---|
| Python | `pyproject.toml` | `uv.lock` | `uv sync --frozen` |
| JS | `package.json` | `bun.lock` | `bun install --frozen-lockfile` |
| Rust | `Cargo.toml` | `Cargo.lock` | `cargo build --locked` |
| **System** | **`bootstrap/<os>.txt`** | (N/A — OS package mgr) | **`make bootstrap`** |

## When you add a new system dependency

1. Add the package name to the right manifest (`apt.txt`, `brew.txt`,
   `winget.txt`) with a brief inline comment explaining why.
2. Re-run `make bootstrap` (or `bootstrap.ps1`) on your dev machine.
3. Note the change in the commit message — future maintainers bootstrap
   from HEAD, not from the PR that originally added the dep.

## Post-install verification (Windows only)

`winget install` for Visual Studio BuildTools 2022 returns success as
soon as the *bootstrapper* lands, even if the C++ workload
(`Microsoft.VisualStudio.Workload.VCTools`) never installed — `cargo
build` then fails with "link.exe not found". `bootstrap.ps1` includes a
post-install verifier that uses `vswhere.exe` to detect the missing
workload and runs `vs_installer.exe modify --add` (passive UI, UAC
may prompt) to finish the install. This keeps the whole bootstrap
idempotent: re-running converges on a fully functional build host.

## Tauri updater signing key (WSL → Windows)

Iteration 2.2 bakes the minisign **public** key into `tauri.conf.json`
for the updater plugin. The matching **private** key was generated
during pre-flight (§1.1.E) and lives at `~/.tauri/aeo-npui.key` on WSL.
For `tauri build` on Windows to emit signed updater artifacts without
exiting non-zero at the tail-of-build signing step, the private key
must also be readable from Windows. When `bootstrap.sh` detects it's
on WSL and the WSL key exists but the Windows copy doesn't, it mirrors
the key to `%USERPROFILE%\.tauri\aeo-npui.key` (same user, so no
cross-account exposure). `scripts/build-windows.ps1` reads that file
and exports `TAURI_SIGNING_PRIVATE_KEY` before invoking `tauri build`.

A pre-existing Windows key is preserved — if the two sides ever
diverge, bootstrap logs the mismatch but doesn't overwrite.

## Pitfall: conda/miniforge3 pkg-config shadowing on Linux

If you have `miniforge3` (or any conda env) earlier on your `PATH` than
`/usr/bin`, its `pkg-config` will shadow the system one with a
restricted `pc_path` that does **not** include
`/usr/lib/*-linux-gnu/pkgconfig`. `cargo build` then fails to find
`webkit2gtk`, `soup-3.0`, `rsvg`, etc. even though the apt packages
are installed. The Makefile pins `PKG_CONFIG=/usr/bin/pkg-config` for
the `desktop` target on Linux to avoid this; if you build outside
`make` (e.g. `bun run tauri dev` directly), set the env var yourself or
prepend `/usr/bin` to `PATH`.

## Relationship to `make ci`

`make bootstrap` is a **one-time setup step**, not part of `make ci`.
`make ci` assumes the system packages are already present and fails
fast (via `cargo build --locked`'s `pkg-config` errors) when they
aren't. If you see a `pkg-config` or WebView2 error from `make ci`,
the fix is `make bootstrap`.

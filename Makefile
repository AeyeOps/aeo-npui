# Makefile for aeo-npui — replaces the retired .github/workflows/ci.yml.
# Same jobs (service, lock-check, no-npm, checker-purity) reproduced as
# .PHONY targets. OS matrix + Windows ty soft-fail dropped — those were
# CI-specific accommodations. `desktop` is a stub until the Iteration 2.1
# Tauri scaffold lands. Run `make` (alias for `make ci`) for the lot.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:
.DEFAULT_GOAL := ci

# Prefer the system pkg-config over any conda/miniforge3 pkg-config that
# may be earlier on PATH — the latter has a restricted pc_path that
# cannot find /usr/lib/*-linux-gnu/pkgconfig entries (webkit2gtk, soup,
# rsvg, …). Falls back to whatever `pkg-config` resolves to on non-Linux
# hosts (macOS brew, Windows tauri-action) where the shadowing issue
# doesn't apply.
PKG_CONFIG_BIN := $(shell test -x /usr/bin/pkg-config && echo /usr/bin/pkg-config || echo pkg-config)

.PHONY: ci all bootstrap build-windows service desktop lock-check no-npm checker-purity version-check version-sync

# Detect WSL so `make ci` can build both halves of the Tauri deliverable
# (Linux cargo `desktop` target + Windows `tauri build` bundles) in a
# single invocation. On pure Linux without Windows interop, build-windows
# is skipped; users still get the `desktop` Linux gate.
ON_WSL := $(shell test -r /proc/version && grep -qiE '(microsoft|wsl)' /proc/version && echo yes || echo no)

ifeq ($(ON_WSL),yes)
CI_BUILD_TARGETS := service desktop build-windows
else
CI_BUILD_TARGETS := service desktop
endif

ci: $(CI_BUILD_TARGETS) lock-check no-npm checker-purity version-check

all: ci

# bootstrap: install OS-native system prerequisites declared in
# bootstrap/<os>.txt. One-time setup per machine; NOT part of `make ci`.
# On WSL, bootstrap.sh also delegates the Windows half to pwsh.exe
# bootstrap.ps1 so both sides of a Tauri build land in one call. On
# native Windows run bootstrap.ps1 directly.
bootstrap:
	bash bootstrap/bootstrap.sh

# build-windows: produce NSIS + MSI Tauri bundles on the Windows host.
# Delegates to scripts/make-windows.sh which stages the repo into a
# Windows-local directory (via $WIN_BUILD_DIR or %TEMP%\aeo-npui-build)
# and invokes scripts/build-windows.ps1 from that CWD inside the VS
# Developer shell. Sync-then-build is required because `bun run tauri
# build` can't execute against the WSL 9P share (Linux-side bun install
# emits symlinks Windows Node can't follow) and because cmd.exe with a
# UNC CWD falls back to C:\Windows and fails silently.
#
# WIN_BUILD_DIR overrides the default staging path:
#   WIN_BUILD_DIR='C:\dev\aeo-npui' make build-windows
build-windows:
	bash scripts/make-windows.sh

# service: lint + type-check + tests for the Python Layer-1 service.
service:
	uv sync --frozen
	cd service
	uv run ruff check
	uv run ty check
	uv run pytest

# desktop: Tauri 2 + Bun + Rust. Assumes system prerequisites from
# `make bootstrap` are already installed (webkit2gtk-4.1 on Linux/WSL,
# MSVC Build Tools + WebView2 on Windows). If `cargo build --locked`
# fails with pkg-config / linker errors, run `make bootstrap` first.
desktop:
	cd desktop
	bun install --frozen-lockfile
	bun run typecheck
	cd src-tauri
	PKG_CONFIG=$(PKG_CONFIG_BIN) cargo build --locked

# lock-check: verify uv.lock matches the manifests without mutating them.
lock-check:
	uv sync --locked

# no-npm: fail if a package-lock.json appears at root, desktop/, or service/.
no-npm:
	test ! -f package-lock.json
	test ! -f desktop/package-lock.json
	test ! -f service/package-lock.json

# checker-purity: enforce single-checker policy (ty only; mypy/pyright/
# pytype/pyre-check/pylance banned). Parses manifests via tomllib/json
# so quoted-and-indented array entries like `"fastapi>=0.135.1"` cannot
# slip past a line-anchored grep. The Python source below is held in a
# `define` block (not a heredoc) because ONESHELL + heredoc tab-stripping
# clobbers Python's significant indentation.
define CHECKER_PURITY_PY
import pathlib, sys, tomllib
banned = {"mypy", "pyright", "pytype", "pyre-check", "pylance"}
hits = []
for p in ("pyproject.toml", "service/pyproject.toml"):
    path = pathlib.Path(p)
    if not path.exists():
        continue
    data = tomllib.loads(path.read_text())
    # runtime deps
    for dep in data.get("project", {}).get("dependencies", []):
        name = dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("~")[0].strip().lower()
        if name in banned:
            hits.append(f"{p}: {dep}")
    # dependency-groups
    for group, deps in data.get("dependency-groups", {}).items():
        for dep in deps:
            name = dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("~")[0].strip().lower()
            if name in banned:
                hits.append(f"{p}:{group}: {dep}")
# desktop/package.json (JSON, not TOML; may not exist yet)
import json
pj = pathlib.Path("desktop/package.json")
if pj.exists():
    doc = json.loads(pj.read_text())
    for section in ("dependencies", "devDependencies"):
        for name in doc.get(section, {}):
            if name.lower() in banned:
                hits.append(f"desktop/package.json:{section}: {name}")
if hits:
    print("Banned type checker(s) found:", *hits, sep="\n  ")
    sys.exit(1)
print("checker purity: ok")
endef
export CHECKER_PURITY_PY

checker-purity:
	uv run python -c "$$CHECKER_PURITY_PY"

# version-check: fail if any shipping manifest drifts from /VERSION.
# Canonical version lives at repo root in VERSION; all per-language
# manifests must match. Bump via `make version-sync` after editing VERSION,
# or use `scripts/version.py bump X.Y.Z` to do both in one step.
version-check:
	uv run python scripts/version.py check

version-sync:
	uv run python scripts/version.py sync

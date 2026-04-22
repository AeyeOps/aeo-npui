---
Title: Python 3.13 workspace pin
Status: Accepted
Date: 2026-04-22
---

## Context

The user's global directive (`~/.claude/CLAUDE.md`) is "Target Python
3.12.3 (aligned with mamba base)." This workspace departs from that
default: `service/pyproject.toml:9` pins
`requires-python = ">=3.13,<3.14"` and `service/pyproject.toml:37`
configures `[tool.ty.environment]` with `python-version = "3.13"`.
Ruff's `target-version = "py313"` at
`service/pyproject.toml:31` mirrors the same choice.

Departing from a user-declared default is a decision that needs an
ADR. An earlier draft justified the 3.13 pin as "the NPU runtime path
needs 3.13-compatible wheels." That claim is not inherently obvious
and was verified before this ADR landed.

## Decision

**Pin Python `>=3.13,<3.14` for the workspace.** Keep the existing pin
in `service/pyproject.toml` unchanged. Apply the same pin to any future
workspace member. The upper bound (`<3.14`) follows the Versioning
Policy's "keep an upper bound so a Python 4 or next-minor release
doesn't silently break CI" rule.

## Verification (conducted 2026-04-22)

Checked published wheel tags for the critical NPU dependency chain on
PyPI, directly from the JSON release metadata:

- `https://pypi.org/pypi/openvino-genai/json` — latest release
  **2026.1.0.0**. Published wheel ABI tags for that release:
  `cp310`, `cp311`, `cp312`, **`cp313`**, `cp314`, `cp314t`.
  Specifically, `openvino_genai-2026.1.0.0-2187-cp313-cp313-win_amd64.whl`
  is published — the Windows NPU path has a cp313 wheel.
- `https://pypi.org/pypi/openvino/json` — latest release
  **2026.1.0**. Published wheel ABI tags: same set, including
  `cp313`.

**Conclusion:** cp313 wheels exist for both `openvino-genai` and
`openvino` on Windows `win_amd64`, Linux `manylinux_2_28_x86_64`,
Linux `manylinux_2_31_aarch64`, and macOS `macosx_11_0_arm64`. The
3.13 pin is compatible with the published wheel surface as of this
date.

An earlier verification draft (authored in parallel during Iteration
1.6) reported "no cp313 wheels published" — that finding was
incorrect. The coordinator re-ran the live JSON fetch and confirmed
cp313 tags in the response, and corrected the ADR. The earlier
incorrect finding was caused by a reading error, not stale PyPI data.
This note is kept to explain the commit history.

Re-verify if this ADR is revisited: a single `curl`+`python -c` probe
against the PyPI JSON endpoint is authoritative.

## Consequences

- The workspace ships on Python 3.13 immediately, without waiting on
  upstream wheel publication.
- Any workspace member added later (e.g. a second Python package)
  inherits the 3.13 pin by default via the uv workspace declaration.
  If a future member cannot tolerate 3.13 (e.g. depends on a library
  without cp313 wheels), the ADR is revisited rather than that member
  getting its own divergent pin.
- The user's global directive (`3.12.3`) remains the default for
  projects *outside* this workspace. `aeo-npui` is explicitly an
  exception, documented here.
- Neither the `Makefile` nor any workspace manifest pins
  `python-version` beyond the `>=3.13,<3.14` range — `uv` installs the
  workspace-declared Python automatically when `make service` (or any
  `uv sync`) runs.
- The Python-version consistency regex in plan §1.3 and §1.12 stays
  as-written: it asserts "no 3.0–3.12 pin anywhere"; any such pin
  would be inconsistent with this ADR and would fail the check.

## Alternatives Considered

**Align with the user global directive (pin 3.12).** Rejected after
verification: `openvino-genai` cp313 wheels are published, so there is
no compatibility forcing function. The workspace can honor the user's
general preference for 3.12 by treating `aeo-npui` as an explicit
exception (documented here) rather than rolling back a pin that was
deliberately raised earlier.

**Pin narrowly to `==3.13.x`.** Rejected: too tight. Both 3.13.0 and
any future 3.13.y patch releases should be acceptable; only 3.14 is
the future unknown worth gating.

**Pin permissively as `>=3.12,<3.14`.** Considered — allows either
3.12 or 3.13 to satisfy the constraint, which is friendlier to
developers who have 3.12 locally. Rejected for Iteration 1: `uv.lock`
captures whichever Python uv resolved against, and CI would need to
matrix both to have real coverage; that doubles CI cost for no
functional gain. Revisit if operators push back.

**Source-build `openvino-genai` locally as a hedge.** Rejected:
irrelevant now that wheels are published. Kept as a fallback only if
upstream stops publishing cp313 wheels in a future release; in that
case, the choice becomes pin-to-3.12 or source-build, and this ADR is
revisited.

## Status

Accepted. The code already matches: `service/pyproject.toml` pins
`>=3.13,<3.14`, `[tool.ty.environment]` pins `3.13`, and ruff's
`target-version` is `py313`. No code change follows from this ADR
beyond correcting the earlier draft's erroneous recommendation.

See also: `service/pyproject.toml:9,31,37` for the current pin; plan
§1.3 and §1.12 for the Python-version consistency regex (asserts "no
non-3.13 pin anywhere" — stays as-written); ADR-009 for why
`openvino-genai` is on the critical path.

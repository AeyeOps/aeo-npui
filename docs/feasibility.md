# Feasibility

Scope: answer one question — *has NPU inference on the target hardware,
driven from WSL, been proven to work?* Implementation choices are
architectural (see [`architecture.md`](./architecture.md)) and/or
recorded as ADRs; this document is evidence and verdict only.

## Verdict

Feasible. The NPU path works on the target profile: the Intel NPU is
present on the Windows host, the Windows-side OpenVINO runtime
selects `NPU` explicitly, a minimal compile-and-inference succeeds
without silent fallback, and the same probe is drivable from WSL and
returns a structured success payload.

Direct WSL-owned Intel NPU access is *not* proven on this hardware
(no `/dev/accel` visible inside WSL, Intel's docs do not list WSL as
a first-class NPU target). The working path is NPU execution on the
Windows host with WSL as the operator environment.

GPU fallback and cloud fallback are explicitly out of scope — see
[`intent.md`](./intent.md) stop conditions.

## Evidence

### Hardware Profile

Target profile is [`intel-core-ultra-win11-wsl`](./profiles/intel-core-ultra-win11-wsl.md).
Verified local machine at time of phase-zero probe (2026-03-20):

- Model: Intel Core Ultra laptop (host model omitted)
- CPU: Intel Core Ultra 7 155H
- NPU: Intel AI Boost (reported by Windows PnP)
- Windows build: 26200
- WSL kernel: 6.6.87.2-microsoft-standard-WSL2

The profile is written broadly enough to cover similar Intel Core
Ultra client systems with Windows 11 host + WSL2 operator environment.

### Upstream Support

- **Windows ML** documents NPU execution as a first-class path on
  Windows 11 24H2+, with Intel NPU systems using the OpenVINO
  execution provider. Source: `learn.microsoft.com/en-us/windows/ai/npu-devices/`.
- **OpenVINO** lists Intel Core Ultra + NPU 3720 as a supported
  target on Windows 11 64-bit. Source: `docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/npu-device.html`.
  WSL is not listed as a first-class Intel NPU target in OpenVINO's
  device docs.

### Phase-Zero Probe Results (2026-03-20)

Four-stage probe (full protocol in [`archive/phase-zero.md`](./archive/phase-zero.md)):

| Probe | Check | Result |
|---|---|---|
| P0-1 | OS-level NPU presence (Windows PnP) | PASS — Intel AI Boost present |
| P0-2 | Runtime-level device enumeration (OpenVINO) | PASS — `NPU` in device list |
| P0-3 | Explicit `NPU` compile + inference, fail-closed | PASS — no silent CPU/GPU fallback |
| P0-4 | WSL-initiated invocation of the Windows probe | PASS — structured payload returned |

Full artifact: [`references/probes/2026-03-20-local-probe.md`](./references/probes/2026-03-20-local-probe.md).

The P0-4 result is the load-bearing one: it proves the cross-OS path
works end-to-end from the operator environment. Everything architectural
in [`architecture.md`](./architecture.md) (Layer 2 orchestration, loopback
HTTP contract, launch parity) is downstream of that result being real.

## What This Does Not Prove

Feasibility of the NPU path on this hardware is not the same as
feasibility of the full product. Separately open questions:

- Which NPU-optimized models are realistic on Core Ultra 155H-class
  hardware for interactive use. Decided per-model, not here.
- Whether the first-shipped Layer-1 implementation should be custom
  OpenVINO Python or OpenVINO Model Server. Captured in ADR-009.
- Whether Iteration-1 port-reservation and autostart work identically
  from both launch origins. That is the architectural-parity claim
  (ADR-003); feasibility is a prerequisite but not a proof.

## Stop Conditions

Restated from [`intent.md`](./intent.md): if the NPU path regresses to
non-working on this profile, or if upstream OpenVINO drops NPU support
for this hardware class, the project stops rather than pivots. There
is no CPU or GPU fallback plan because a fallback plan would weaken
the project goal and hide NPU regressions.

# Phase Zero

> **STATUS:** Passed 2026-03-20. Kept as proof of feasibility. Not a forward plan.
>
> Current plans live under [`../roadmap/`](../roadmap/); decisions that
> superseded this document are catalogued in
> [`../decisions/`](../decisions/).

## Purpose

Phase zero exists to answer one question only:

Can this Windows 11 host expose a real Intel NPU execution path that we can drive from our WSL workflow?

If the answer is not clearly yes, we stop. No controller, no model router, no local LLM service framework.

## Success Criteria

Phase zero passes only if all of the following are true:

1. Windows reports the Intel NPU device at the OS level.
2. A supported Windows-side runtime reports an `NPU` device.
3. A minimal NPU-targeted compile or inference succeeds without silent fallback to CPU or GPU.
4. The same probe can be launched from WSL and returns a machine-readable result.

If any step fails, the phase is incomplete.

## Non-Goals

- no OpenAI-compatible API
- no OVMS service yet
- no model catalog
- no alternate accelerator path

## Lean Stack Choice

Use native Windows Python plus OpenVINO for the proof.

Why this is the leanest useful choice:

- smaller surface area than a model server
- direct device enumeration path
- direct explicit device target via `NPU`
- already aligned with the Intel Windows NPU path from the earlier research

Windows ML remains a valid later option, but it is not the smallest proof path.

When running Windows-side Python for this phase, use the existing conda environment:

```powershell
conda activate npu
```

## Experiments

### P0-1. OS-level NPU detection

Run a Windows command that proves the host exposes the Intel NPU device.

Minimal example:

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object { $_.FriendlyName -match "NPU|Neural|AI Boost|Intel.*AI" } |
  Select-Object Status,Class,FriendlyName,InstanceId
```

Pass condition:

- the Intel NPU appears as a present device

Failure condition:

- no NPU device appears

### P0-2. Runtime-level device enumeration

Run a minimal Windows-side OpenVINO probe that enumerates available devices.

Target behavior:

- `NPU` appears in the runtime device list

Pass condition:

- the probe returns a device list containing `NPU`

Failure condition:

- runtime installs but only reports CPU or GPU

### P0-3. Minimal NPU-targeted compile or inference

Run the smallest explicit `NPU` execution attempt we can manage.

Requirements:

- request `NPU` explicitly
- do not permit silent success on CPU or GPU
- capture the chosen device in the output

Pass condition:

- compile or inference completes with `NPU` explicitly selected

Failure condition:

- the probe falls back to CPU or GPU
- the runtime accepts the request but cannot initialize the NPU path

### P0-4. WSL-driven host invocation

From WSL, invoke the same Windows probe and capture a structured result.

This proves the operator path we actually care about:

- daily control from WSL
- NPU execution on the Windows host

Pass condition:

- WSL can trigger the Windows probe
- the probe returns a structured success payload
- the default invocation path uses `pwsh.exe`

Failure condition:

- the probe only works interactively from Windows
- the WSL call path breaks quoting, environment lookup, or host access

## Proposed Deliverables

Keep the deliverables tiny:

- one Windows-side probe script
- one WSL launcher wrapper that calls `pwsh.exe`
- one JSON report shape
- one markdown runbook

That is enough to validate the platform decision.

## Proposed Report Shape

The probe output should be machine-readable and fail closed.

Example fields:

- `timestamp`
- `host_model`
- `windows_build`
- `wsl_kernel`
- `npu_present_os`
- `npu_present_runtime`
- `requested_device`
- `actual_device`
- `compile_ok`
- `inference_ok`
- `error`

## Phase-Zero Acceptance Artifact

The phase is only complete when we can save a real run artifact showing:

- OS-level NPU presence
- runtime-level NPU presence
- explicit `NPU` selection
- success or failure with a clear reason

Screenshots are optional. Structured output is required.

## Decision Rule After Phase Zero

If phase zero passes:

- proceed to a minimal Windows-hosted worker and WSL wrapper

If phase zero fails:

- stop the NPU worker design
- record the failure mode
- stop the project rather than pivot to another accelerator

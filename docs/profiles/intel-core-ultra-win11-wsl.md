# Intel Core Ultra Windows 11 + WSL Profile

## Profile ID

`intel-core-ultra-win11-wsl`

## Intent

Support Intel Core Ultra laptops where:

- Windows 11 is the real hardware host
- WSL 2 is the daily operator environment
- Intel NPU is the required local LLM accelerator

## Verified Local Machine

The current environment reports:

- Model: Intel Core Ultra laptop (host model omitted)
- CPU: Intel Core Ultra 7 155H
- NPU: Intel AI Boost
- GPU: NVIDIA GeForce RTX 4050 Laptop GPU
- Integrated GPU: Intel Arc Graphics
- Windows build: 26200
- WSL kernel: 6.6.87.2-microsoft-standard-WSL2

The profile is written broadly enough to cover similar Intel Core Ultra client systems (Core Ultra 1xx-series, Windows 11 24H2+, WSL2 operator environment).

## Runtime Decision

### Default

- Run the NPU runtime on native Windows
- Access it from WSL over localhost or direct process launch

## Why

- Windows-side Intel NPU support is clearly documented
- direct WSL NPU access is not the best-supported path from the sources reviewed
- phase zero already proved explicit NPU execution from WSL through the Windows host

## Driver / Runtime Expectations

### Windows host

- Intel NPU driver installed
- OpenVINO runtime or OVMS available
- explicit `NPU` execution path

### WSL guest

- launcher and client tooling

## Acceptance Criteria For This Profile

The profile should be considered working only if all of the following pass:

1. A local request from WSL reaches the Windows NPU worker over localhost.
2. The worker serves a chat/completions-style request successfully.
3. Windows shows real NPU activity during the request.
4. The runtime records that NPU was selected.
5. There is no implicit fallback to CPU or GPU.

## Known Constraint

If the NPU path is not viable, this project should stop rather than pivot to a different accelerator path.

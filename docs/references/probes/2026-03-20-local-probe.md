# Local Probe - 2026-03-20

This note captures what the current machine exposed during initial feasibility work.

## WSL Kernel

Command:

```bash
uname -a
```

Key result:

- `Linux DESKTOP-EXAMPLE1 6.6.87.2-microsoft-standard-WSL2 ... x86_64`

## Linux Device Exposure

Command:

```bash
ls -ld /dev/dxg /dev/accel /dev/dri
ls -l /dev | rg -i 'vpu|npu|accel|dxg'
```

Key result:

- `/dev/dxg` exists
- `/dev/accel` does not exist
- no obvious NPU or VPU node was visible in the guest

Interpretation:

- WSL has GPU interop visibility
- Intel NPU is not obviously surfaced into the guest as a Linux device node on this machine

## Windows Version

Command:

```powershell
Get-CimInstance Win32_OperatingSystem |
  Select-Object Version,BuildNumber,Caption
```

Key result:

- Windows 11 Pro
- Version `10.0.26200`
- Build `26200`

## Host Identity

Command:

```powershell
Get-ComputerInfo |
  Select-Object CsSystemFamily,CsModel,CsProcessors,OsName,OsVersion,OsBuildNumber
```

Key result:

- System family: `(example laptop family)`
- Model: `Example Laptop 14`
- Processor: `Intel(R) Core(TM) Ultra 7 155H`

## NPU Detection

Command:

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object { $_.FriendlyName -match "NPU|Neural|AI Boost|Intel.*AI" } |
  Select-Object Status,Class,FriendlyName,InstanceId
```

Key result:

- `Intel(R) AI Boost`

## GPU Detection

Command:

```powershell
Get-CimInstance Win32_VideoController |
  Select-Object Name,PNPDeviceID,DriverVersion
```

Key result:

- `NVIDIA GeForce RTX 4050 Laptop GPU`
- `Intel(R) Arc(TM) Graphics`

## CUDA In WSL

Command:

```bash
nvidia-smi
```

Key result:

- `Driver Version: 581.95`
- `CUDA Version: 13.0`
- RTX 4050 visible from WSL

## Bottom Line

The current machine is a good fit for the proposed hybrid profile:

- Intel NPU exists on the Windows host
- WSL has working NVIDIA CUDA visibility
- direct Intel NPU visibility from WSL was not observed in the initial probe

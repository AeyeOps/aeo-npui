# Console Native

Browser-capable React Native UI for the NPU console, built with Expo SDK 55.

## Run

1. Start the backend API:

```bash
cd /opt/aeo/aeo-infra/npu/console
uv run npu-console serve --host 127.0.0.1 --port 8765
```

2. Start the Expo web app:

```bash
cd /opt/aeo/aeo-infra/npu/console-native
npm run web
```

## Windows Chrome CDP From WSL

This repo includes a WSL-to-Windows Chrome CDP workflow for browser automation without relying on Linux Chrome or WSLg.

Defaults:

- Windows Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Profile root: `C:\dev\chrome-profile`
- WSL profile path: `/mnt/c/dev/chrome-profile`
- Profile directory: `Default`
- CDP port: `9222`
- Target URL: `http://127.0.0.1:19006`

Commands:

```bash
cd /opt/aeo/aeo-infra/npu/console-native

# Launch a fresh Windows Chrome instance on the fixed CDP port
npm run chrome:cdp:start

# Repair the persisted profile exit type if needed
npm run chrome:cdp:prepare-profile

# Verify the port is live
npm run chrome:cdp:probe

# Attach from WSL Playwright over CDP and save a screenshot
npm run chrome:cdp:attach

# Stop the Chrome instance launched on that CDP port
npm run chrome:cdp:stop
```

Artifacts:

- CDP validation screenshot: `output/windows-chrome-cdp.png`

Overrides:

```bash
NPU_WINDOWS_CHROME_CDP_PORT=9333 \
NPU_WINDOWS_CHROME_PROFILE_ROOT='C:\dev\chrome-profile-alt' \
npm run chrome:cdp:start
```

Notes:

- This repo does not contain a browser MCP server to patch directly. The CDP/profile behavior is wired into repo-local helper scripts and npm commands instead.
- The launch script uses a clean Windows profile root by default and forces a fresh Chrome run for consistent CDP ownership.
- Startup suppression is handled in two places:
  - launch flags suppress default-browser prompts
  - the profile repair step rewrites `profile.exit_type` to `Normal` so reused runs do not keep surfacing restore-session UI

## Optional API Override

The app defaults to `http://127.0.0.1:8765`.

To target a different API URL:

```bash
EXPO_PUBLIC_NPU_API_BASE_URL=http://127.0.0.1:9000 npm run web
```

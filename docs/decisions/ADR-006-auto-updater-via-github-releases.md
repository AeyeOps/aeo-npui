---
Title: Auto-updater via GitHub Releases with latest.json
Status: Accepted
Date: 2026-04-22
---

## Context

The product is installed on operator Windows machines and must stay
current with security fixes, bug fixes, and NPU-runtime improvements.
Manual "download the new MSI and reinstall" is friction that defers
updates; an auto-updater with signature verification removes the
friction.

Tauri 2 ships a first-party updater plugin (`@tauri-apps/plugin-updater`)
that:

- reads an `endpoints` URL from `tauri.conf.json` → `plugins.updater`
- fetches a `latest.json` manifest describing the newest version
- if the installed version is older, downloads the update bundle
- verifies the bundle against an ed25519 public key embedded in
  `tauri.conf.json`
- installs and restarts the app

Three surfaces need to agree:

1. **Where `latest.json` lives.** Any HTTPS URL works; we need one
   that's free, durable, reliably reachable from the operator's
   Windows machine, and part of the existing build pipeline.
2. **Who builds and signs the update bundle.** The `tauri-action`
   GitHub Action builds the installer, produces a Tauri updater
   signature from a keypair, and publishes to GitHub Releases.
3. **Where the keys live.** The public key is committed to
   `tauri.conf.json` (it has to be — the client verifies against it).
   The private key lives in a GitHub repository Secret named
   `TAURI_SIGNING_PRIVATE_KEY`.

## Decision

**Updater endpoint: GitHub Releases.**

`tauri.conf.json → plugins.updater.endpoints` is set to:

```
https://github.com/AeyeOps/aeo-npui/releases/latest/download/latest.json
```

GitHub's `/releases/latest/download/<asset>` redirects to the asset on
the newest (non-prerelease) release, which means the URL is stable and
the manifest pointer updates automatically when a new tag is published.

**Build and sign: `tauri-apps/tauri-action@v0`.**

The release workflow (`.github/workflows/release.yml`, plan §5.3):

1. Checks out the tagged ref.
2. Installs Bun, Rust, uv.
3. Runs `bun install --frozen-lockfile`.
4. Invokes `tauri-apps/tauri-action@v0` with
   `projectPath: desktop`, `tauriScript: 'bun run tauri'`, and Windows
   targets.
5. `tauri-action` builds MSI + NSIS, signs each with the Tauri updater
   keypair, generates `latest.json`, and uploads all three (plus the
   signature files) to the GitHub Release.
6. SignPath signing (ADR-007) wraps the `.exe`/`.msi` with Authenticode
   — orthogonal to the Tauri updater's ed25519 signature.

**Keypair lifecycle:**

- **Generated once** in pre-flight step 1.1.E via `bunx
  @tauri-apps/cli@^2 signer generate -w ~/.tauri/aeo-npui.key`.
  The `@^2` major pin matters: without it, bunx may resolve a stale
  v1 release.
- **Public key** (`~/.tauri/aeo-npui.key.pub`) is embedded into
  `tauri.conf.json → plugins.updater.pubkey`. The real pubkey lives
  there from the first commit of the config file in Iteration 2.2.
  No placeholder ever ships.
- **Private key** contents go into the repo's `TAURI_SIGNING_PRIVATE_KEY`
  GitHub Secret. If the keypair was created with a password, the
  password goes into `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (GitHub
  rejects empty-string Secrets, so the Secret is only created if a
  password was used — plan §1.1.E and §5.1).

## Consequences

**Easier:**

- Zero hosting cost. GitHub Releases is the CDN; the domain is
  `github.com` (trusted by corporate Windows networks).
- Zero extra infra to maintain. The manifest generator is
  `tauri-action`; the storage is GitHub.
- Signature verification is end-to-end: installer → Tauri verifies
  bundle signature before applying, independent of the TLS chain.
- Update bundles are orthogonal to the SignPath Authenticode
  signature (ADR-007); either can be added/removed without touching
  the other.

**Harder:**

- If GitHub is unreachable (e.g. operator on a restricted corporate
  network), auto-update fails. Documented behavior: updater prompts
  are non-blocking; the app keeps working on the installed version.
- The `@^2` pin in the `bunx` command for keypair generation is a
  manual discipline; without it, a stale Tauri 1 CLI can silently
  generate an incompatible key format. Plan §1.1.E flags this
  explicitly.
- Key loss is unrecoverable. If `~/.tauri/aeo-npui.key` is destroyed
  before it is ever pushed to Secrets, the keypair must be regenerated
  and `tauri.conf.json` re-committed; existing installs cannot auto-
  update to a build signed with the new key — they must be reinstalled
  manually. The key material MUST be backed up outside the dev
  machine (e.g. a password manager) after generation.

**New work that follows:**

- Iteration 2.2 embeds the real pubkey into `tauri.conf.json`.
- Iteration 5.1 verifies the pipeline end-to-end: dry-run build signs
  an update bundle, password-Secret semantics are confirmed.
- Iteration 5.4 tags v0.0.1, then v0.0.2, and verifies the installed
  app auto-updates.

## Alternatives Considered

**Self-hosted `latest.json` on an AeyeOps-owned domain.** Rejected:
adds hosting cost, adds TLS cert maintenance, adds CDN considerations
(updater traffic is small but bursty at release time), and adds a
failure mode that GitHub Releases does not have (our CDN being down).
No upside unless corporate networks block github.com specifically,
which is rare for open-source projects.

**S3 / Azure Blob / Cloudflare R2.** Same trade-off as self-hosted —
adds a cloud account and a bill. Revisit only if GitHub rate-limits
become an issue.

**Windows Update / Microsoft Store.** Rejected: operator-targeted
product does not need Store distribution; Store certification would
add weeks per release. Microsoft Store's updater also does not match
the trust model — we want ed25519 bundle signatures verifiable by the
installed app, not just TLS + Store publisher signing.

**Chocolatey / winget.** Deferred (not rejected). Both are viable
distribution channels; neither handles auto-update the way Tauri's
plugin does. Revisit if users request package-manager install.

**No auto-updater; users run the new MSI manually.** Rejected:
experience from other products in the space shows operators defer
manual updates indefinitely. Security-relevant fixes are not
time-to-patch without auto-update.

## Status

Accepted. Pubkey lives in `tauri.conf.json` from Iteration 2.2. Release
workflow lands in Iteration 5.3. Signing semantics and dry-run
verification in Iteration 5.1. See ADR-004 for the Tauri shell that
hosts the updater plugin, ADR-007 for the separate Authenticode
signing layer.

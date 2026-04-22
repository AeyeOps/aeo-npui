---
Title: Code signing via SignPath Foundation (OSS program)
Status: Accepted
Date: 2026-04-22
---

## Context

Windows has two independent signature layers that matter for a
distributed desktop app:

1. **Authenticode** — the Microsoft-standard signature on Windows
   executables and installers. Unsigned installers trigger SmartScreen
   "Unknown publisher" warnings. Signed installers from an unknown
   publisher still accrue a SmartScreen reputation warning until
   ~1000+ downloads. Signed installers from a reputable publisher
   silently install.
2. **Tauri updater signature** — ed25519-signed update bundles that
   `@tauri-apps/plugin-updater` verifies at install time (ADR-006).
   Orthogonal to Authenticode.

Authenticode signing requires a commercial code-signing certificate.
Options:

- **Paid commercial certificate** (DigiCert, Sectigo, etc.) — $400–
  $700/year, plus hardware HSM requirements introduced by the 2023
  baseline change that mandates key storage on a certified HSM for all
  new standard certificates.
- **Extended Validation (EV) certificate** — $700–$1000/year, instant
  SmartScreen reputation. Overkill for an OSS project.
- **SignPath Foundation OSS program** — free Authenticode signing for
  qualifying open-source projects. Uses a cloud HSM, integrates with
  GitHub Actions via `signpath/github-action-submit-signing-request@v1`.

SignPath Foundation eligibility (verified 2026-04 at signpath.org/org):

- Project must be under an OSI-approved open-source license (MIT
  qualifies).
- Source code must be publicly accessible from day one — SignPath
  verifies build provenance against the public repo.
- MFA (two-factor authentication) is required on every committer's
  GitHub account; SignPath can deny signing if an account with push
  access lacks MFA.
- Approval is not instant; review typically takes days.

## Decision

**Code signing is done via SignPath Foundation's OSS program.**

Enabling conditions (hard requirements from SignPath, all satisfied by
this plan):

- **MIT license** is committed to the repo root from Iteration 1.3.
- **Public repo from day 1** — `AeyeOps/aeo-npui` is created public
  per plan pre-flight 1.1.B. Creating private and flipping later is
  possible but adds a coordination step with SignPath reviewers;
  avoiding that is cheaper than reversing it.
- **MFA on all committer GitHub accounts** — every human with push
  access to `AeyeOps/aeo-npui` must have 2FA enabled. GitHub org
  settings can enforce this; SignPath will spot-check.

Integration path (plan §5.2, §5.3):

1. SignPath OSS application is filed in pre-flight 1.1.C. Form is
   ~30 minutes; review is days. Iteration 5 is the earliest point
   where signing must actually work.
2. `.github/workflows/release.yml` has a SignPath step guarded by a
   condition:
   ```
   if: github.event_name == 'push' || inputs.signpath_enabled == 'true'
   ```
   A push-tag release always signs (production path). A manual
   `workflow_dispatch` dispatch signs only when the operator flips
   `signpath_enabled=true`.
3. Before SignPath approval lands, the release workflow can still
   produce installers — they ship unsigned (Tauri updater signature
   still valid) and operators see a SmartScreen warning. Once
   approved, a re-tag or a `workflow_dispatch` with the flag flipped
   produces signed installers.

## Consequences

**Easier:**

- Zero cost for code signing. For an operator-facing tool this is
  material: commercial code signing is a $500+/year line item that
  the project does not otherwise need.
- Cloud HSM is SignPath's responsibility, not ours. No hardware key
  management, no USB dongle rotation, no "where did we put the
  signing cert" 18 months from now.
- Build provenance is cryptographically verifiable by SignPath against
  the public repo — this is a security win over self-managed signing,
  where the developer's laptop holds the key.

**Harder:**

- **Approval is not instant.** The first signed release can ship only
  after SignPath OSS review completes. Plan §5.3's
  `workflow_dispatch` toggle exists specifically to ship unsigned
  first if needed, so the release pipeline is not blocked on a
  dependency we do not control.
- The public-repo-from-day-1 constraint ripples. Staging the repo as
  private and flipping public later would require re-filing the
  SignPath application. Plan pre-flight 1.1.B is explicit: repo is
  public from creation.
- MFA becomes a contributor-onboarding step. Any new committer must
  enable 2FA on their GitHub account before being added to the org.

**New work that follows:**

- Pre-flight 1.1.C: user files SignPath OSS application (after 1.3
  lands the LICENSE and 1.1.B creates the public repo).
- Iteration 5.2: integrate the SignPath GitHub Action into
  `release.yml` after approval.
- Iteration 5.3: the workflow's conditional signing step is wired
  before approval, so the toggle works on day 1.

## Alternatives Considered

**Buy a standard commercial Authenticode certificate.** Rejected:
cost (~$500/year) and HSM-on-laptop is an ongoing operational burden
the project does not need to carry for an OSS delivery. Revisit only
if SignPath declines our application.

**Buy an EV certificate for instant SmartScreen reputation.**
Rejected: ~$1000/year and adds a hardware token to the release
pipeline. SignPath's cloud HSM + standard Authenticode + time (to
accrue reputation) is the right shape for an OSS project.

**Ship unsigned. Tell users to accept the SmartScreen warning.**
Rejected: SmartScreen warnings are a real install friction and erode
user trust. The Tauri updater ed25519 signature is NOT a substitute —
it's an in-app verification, not a pre-install one.

**Ship only the MSI (skip NSIS) and use Microsoft Store signing.**
Rejected: Store certification adds weeks per release and does not
match the direct-download distribution model. Also does not help
direct-from-GitHub-Releases downloaders.

**Use a self-signed certificate added to the operator's trusted
root.** Rejected: this works only for internal/enterprise deployment
and defeats the "download from GitHub, install anywhere" use case.

## Status

Accepted. MIT LICENSE commits in Iteration 1.3. Repo is public from
Iteration 1.1.B. SignPath application is filed in 1.1.C. Workflow
integration in 5.2/5.3. See ADR-006 for the orthogonal Tauri updater
signing; that one does NOT depend on SignPath approval and ships from
Iteration 2 onward.

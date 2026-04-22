# Console Native PRD

## Product

NPU Console Native

Browser-capable React Native operator workspace for the local Intel NPU flow.

## Why This Exists

The Python TUI solved a useful interaction model but is too fragile as the primary operator surface. The next rounds should keep the server-side foundation intact:

- persistent local chat session
- prompt construction and continuity
- event-log-driven metrics
- artifact and endurance summaries
- command semantics such as `/clear`, `/quit`, and log inspection

The UI layer should become a deliberate browser app, not a terminal emulation in a new shell.

## Frontend Skill Framing

**Visual thesis**

A restrained operator workspace: calm dark surface, one strong accent, dense but breathable telemetry, and a chat surface that feels deliberate rather than improvised.

**Content plan**

1. Primary workspace: transcript or log, depending on mode
2. Support: status, active model/session, selected command
3. Detail: metrics, interaction rail, artifact and endurance context
4. Final action: composer and command affordances

**Interaction thesis**

1. Startup should feel like an intentional warm-up sequence, not a polling race.
2. View changes should feel like moving between work surfaces, not toggling cards.
3. Log follow, transcript updates, and metrics refreshes should feel stable and calm.

## UX Contract To Preserve

- Startup has explicit `starting`, `ready`, and `failed` states.
- A first user prompt must never disappear or need retyping.
- Transcript continuity and `/clear` semantics remain correct.
- The operator can move between chat, metrics, and log without losing context.
- The live interaction rail remains visible somewhere in the split workspace.
- Log follow is intelligible, reversible, and stable.
- Desktop and mobile both preserve a clear “one working surface + one context rail” structure.

## Current Baseline

Validated against the current implementation with Playwright on Expo web:

- Desktop snapshot: `output/playwright/.playwright-cli/page-2026-03-21T14-27-37-072Z.yml`
- Desktop screenshot: `output/playwright/.playwright-cli/page-2026-03-21T14-28-32-070Z.png`
- Mobile snapshot: `output/playwright/.playwright-cli/page-2026-03-21T14-27-53-100Z.yml`
- Mobile screenshot: `output/playwright/.playwright-cli/page-2026-03-21T14-27-54-284Z.png`

Current product risks:

- `/quit` is not cancellation-safe if startup is still loading.
- First prompt can be dropped during startup.
- Log follow will stall after the log window reaches a fixed length.
- The browser app does not yet render the backend interaction rail.
- The shell is still card-heavy and utility-correct, but not yet visually composed as a strong primary workspace.

## Goals

- Make the browser app the default operator surface.
- Preserve the backend session/metrics foundation.
- Recompose the UI into a restrained workspace rather than a set of stacked info cards.
- Make validation part of each increment, not a final cleanup step.

## Non-Goals

- No new inference features in these rounds.
- No major backend-runtime redesign beyond what is required to preserve current behavior safely.
- No mobile-native packaging in these rounds; browser-first Expo web is the immediate target.

## Rounds

### Round 1: Interaction Contract and State Safety

Focus:

- remove prompt loss
- make stop/start semantics safe
- stabilize the API contract the UI will build on

Exit criteria:

- startup, send, clear, and stop all behave deterministically
- browser refreshes do not create zombie or resurrected sessions
- Playwright can prove the startup-to-ready transition and first-prompt retention

### Round 2: Workspace Recomposition

Focus:

- restore the missing interaction rail
- reduce card treatment
- make the split view feel like one workspace with a secondary inspector

Exit criteria:

- the main surface communicates “chat/log first, context second”
- interaction rail is visible and useful in split mode
- desktop view reads clearly in one scan without scrolling

### Round 3: Log, Metrics, and Mobile Fit

Focus:

- fix log follow behavior
- tighten responsive structure
- make metrics and endurance context readable without visual clutter

Exit criteria:

- log follow works after long sessions
- mobile no longer feels like a squeezed desktop
- desktop and mobile each have a stable primary surface and a readable context rail

### Round 4: Motion, Polish, and Release Gate

Focus:

- add a small number of meaningful motions
- tune typography, spacing, and contrast
- formalize browser QA inventory and artifact capture

Exit criteria:

- motion improves presence without noise
- screenshots support the quality claims
- the UX can be signed off with explicit desktop and mobile evidence

## Parallelization and Sequencing

Sequential:

1. Round 1 must complete first. State safety and prompt retention are prerequisite to trustworthy UI work.
2. The core desktop composition task in Round 2 must land before mobile compression and motion polish.
3. Final release QA in Round 4 must run after all preceding rounds.

Parallelizable after Round 1:

- desktop workspace recomposition
- interaction rail restoration
- log follow implementation
- endurance side-context cleanup

Parallelizable after Round 2 desktop shell is stable:

- mobile responsive adaptation
- typography and spacing polish
- motion pass prototypes

## Validation Model

Every roadmap item must ship with:

- one functional browser check
- one visual check at the state where the feature matters
- desktop evidence at `1600x900`
- mobile evidence at `390x844`
- at least one negative confirmation of what was checked and not found

Playwright workflow for each increment:

1. Start API: `uv run npu-console serve --host 127.0.0.1 --port 8765`
2. Start Expo web: `EXPO_PUBLIC_NPU_API_BASE_URL=http://127.0.0.1:8765 npx expo start --web --port 19006`
3. Run browser QA at desktop width.
4. Run browser QA at mobile width.
5. Save snapshots and screenshots under `output/playwright/`.

## Deliverables In This Roadmap Folder

- `console-native-prd.md`: product framing, rounds, sequencing, and QA contract
- `console-native-tasks.yaml`: task tracker with dependencies, validation, and status fields

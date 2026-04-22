# Archive

Historical planning docs. Kept because they record *how we got here* —
why the current architecture looks the way it does — but they are not
forward plans. Do not resurrect instructions from these files without
confirming the instruction has not been superseded.

## Contents

| File | What it was | Forward pointer |
|---|---|---|
| [`phase-zero.md`](./phase-zero.md) | Go/no-go feasibility probe for NPU execution. Passed 2026-03-20. | Proof of feasibility lives here; current plans live in [`../roadmap/`](../roadmap/). |
| [`2026-03-operator-console-plan.md`](./2026-03-operator-console-plan.md) | Original Rich + Typer TUI operator console plan. | [`../decisions/ADR-001-rich-typer-tui-demoted.md`](../decisions/ADR-001-rich-typer-tui-demoted.md); forward plan in [`../roadmap/native-ui.md`](../roadmap/native-ui.md). |
| [`2026-03-operator-console-cleanup-plan.md`](./2026-03-operator-console-cleanup-plan.md) | Cleanup scope for the TUI (event types, metrics, endurance artifact shape). | Event/metrics/endurance contracts extracted into [`../contracts/`](../contracts/). |
| [`2026-03-operator-console-e2e-recovery-plan.md`](./2026-03-operator-console-e2e-recovery-plan.md) | E2E-first testing rationale (PTY, width wrap, snapshot regressions). | Kept-learnings in [`../testing.md`](../testing.md); TUI specifics superseded by ADR-001. |
| [`2026-03-dashboard-recovery-plan.md`](./2026-03-dashboard-recovery-plan.md) | TUI dashboard recovery tactics (startup-state drift, input event handling). | Superseded by ADR-001; informs the cross-launch parity invariant in [`../testing.md`](../testing.md). |
| [`2026-03-console-native-prd.md`](./2026-03-console-native-prd.md) | Expo/React Native PRD for a native console. | Superseded by [ADR-004 (Tauri 2)](../decisions/ADR-004-native-shell-is-tauri-2.md) and [`../roadmap/native-ui.md`](../roadmap/native-ui.md). |

## Why archive instead of delete?

Four reasons:

1. **Cross-reference integrity.** ADRs cite these plans by name.
   Deleting breaks the audit trail.
2. **Regression proof.** If the TUI or Expo path comes back up, the
   archive shows what already failed and why. Cheaper than re-learning.
3. **Cross-launch test baseline.** Archived plans name the concrete
   symptoms (width-wrap inflation, raw-input drops) that the new
   Playwright + `tauri-driver` harness uses as the regression floor.
4. **Commit-history honesty.** `git archive` preserved only tracked
   files in the extraction; the archive fixes forward paths so
   references still resolve after the path renames.

---
Title: Frontend toolchain is Bun (pm + runner) + Vite (bundler + dev server)
Status: Accepted
Date: 2026-04-22
---

## Context

The desktop frontend (`desktop/`) is a React + TypeScript app bundled
inside a Tauri 2 shell (ADR-004). A toolchain choice has several
independent axes:

- **Package manager** — npm vs Yarn vs pnpm vs Bun
- **Script runner** — the `bun run <script>` / `npm run <script>`
  lifecycle layer
- **Bundler / dev server** — Vite vs Webpack vs esbuild vs Bun's
  experimental bundler
- **Test runner** — Vitest vs Jest vs Playwright (E2E; see ADR-012)

The project constraints:

- Single lockfile policy (`bun.lockb` on Bun ≤1.1, `bun.lock` on Bun
  ≥1.2) — no `package-lock.json` anywhere (CI guard in plan §1.11).
- Tauri 2's `bun run tauri` script needs to orchestrate both the dev
  server and the Rust build; `tauri-action` in the release workflow
  needs `tauriScript: 'bun run tauri'` so it does not default to npm
  (plan §5.3).
- E2E tests use `@playwright/test` via `tauri-driver` (Iteration 3.5).
- HMR (hot module replacement) during `bun run tauri dev` is a
  quality-of-life requirement; the dev loop is Vite-served and Tauri
  auto-reloads the WebView when Vite pushes updates.

Bun is attractive as a unified runtime: package manager, script runner,
TypeScript transpiler, test runner, and bundler in one binary. In
practice (as of 2026-Q1), Bun's package manager and script runner are
mature and ~10× faster than npm for install + script-start; Bun's
bundler, however, is still marked experimental and lacks the
plugin/middleware ecosystem that Vite carries.

## Decision

**Bun is the package manager and script runner.** `bun install`
resolves deps, `bun run <script>` invokes lifecycle scripts, the
workspace lockfile is Bun's.

**Vite is the bundler and dev server.** `desktop/vite.config.ts`
defines the React plugin, the dev-server port, the HMR hook that
Tauri's dev loop reads. `bun run tauri dev` invokes Vite under the
hood; `bun run build` produces the production bundle Tauri packages.

The roles do not overlap. Bun handles "install dependencies and
orchestrate scripts"; Vite handles "compile TS, serve dev, bundle
prod."

## Consequences

**Easier:**

- Install speed: `bun install` on a warm cache is sub-second;
  `bun install --frozen-lockfile` in CI is competitively fast.
- No `package-lock.json` drift — Bun's lockfile is the only one.
- Vite's React/TypeScript/HMR plugin ecosystem is the widest
  available; `@vitejs/plugin-react`, path-alias resolution, and
  asset handling work out of the box.
- Tauri's own scaffold (`bunx create-tauri-app ... --template
  react-ts --manager bun`) wires Bun + Vite by default; no custom
  glue is needed.
- Playwright and `tauri-driver` both run under Bun-executed scripts
  without modification.

**Harder:**

- Two tools to learn (Bun semantics + Vite semantics) instead of one.
  The cost is modest: Bun's `bun run` mirrors npm, and Vite's config
  is widely documented.
- Bun occasionally has subtle incompatibilities with
  `node_modules`-assuming tools; when that happens, the workaround is
  usually to invoke the tool via `bun run` (not `bun x`) so it picks up
  the expected PATH/resolution. Record any instance we hit as a
  follow-up note.

**New work that follows:**

- `desktop/package.json` declares `vite`, `@vitejs/plugin-react`,
  `react`, `react-router-dom`, `@tauri-apps/api`,
  `@tauri-apps/plugin-updater`, `@playwright/test` — all as `>=`
  minimums, lockfile is the truth (plan versioning policy).
- `desktop/vite.config.ts` is committed; it is the source of truth for
  the dev-server port that the Tauri config's CSP references.
- CI enforces the no-npm guard: `test ! -f desktop/package-lock.json`
  (plan §1.11).

## Alternatives Considered

**Bun bundler (skip Vite entirely).** Rejected for now: at the time of
this decision, Bun's bundler is still experimental, the dev-server DX
gap vs Vite is real (HMR patterns, plugin ecosystem), and the React +
Tauri + tauri-driver path is battle-tested with Vite. Revisit in 12–18
months once Bun's bundler has a stable plugin API and feature parity
with Vite's React plugin.

**npm + Vite.** Rejected: gives up Bun's install-speed advantage and
introduces a second lockfile (npm's) that the workspace policy
forbids. No upside.

**pnpm + Vite.** Rejected: pnpm's workspace ergonomics are excellent,
but the team is already choosing Bun elsewhere (its script runner is
faster for the Tauri dev loop) and the mixed story (pnpm for pm, Bun
for runtime) has no advantage over Bun-for-both-pm-and-runner.

**Webpack + Bun.** Rejected: Webpack's configuration burden for a
modern React + TS app is strictly higher than Vite's, and the dev-loop
HMR is slower. No project constraint benefits from Webpack.

**esbuild directly (without Vite's plugin layer).** Rejected: Vite
already uses esbuild internally for TS transpilation; going directly
gives up the React Fast Refresh integration and the dev-server
middleware story.

## Status

Accepted. Bun is installed in CI via `oven-sh/setup-bun@v1` (plan
§5.3 step 2, §1.11 desktop job when live). Vite is declared in
`desktop/package.json`. The split is durable until Bun's bundler
reaches the maturity bar; revisit annually. See ADR-004 for the
shell, ADR-006 for how `bun run tauri build` feeds the release
pipeline.

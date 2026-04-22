import { useEffect, useState } from "react";
import "./App.css";

const HEALTH_URL = "http://127.0.0.1:8765/health";
const POLL_MS = 5000;

type ConnectionState = "unknown" | "ok" | "down";

const STATE_TEXT: Record<ConnectionState, string> = {
  unknown: "checking…",
  ok: "connected",
  down: "disconnected",
};

function App() {
  const [state, setState] = useState<ConnectionState>("unknown");
  const [lastCheck, setLastCheck] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      let next: ConnectionState = "down";
      try {
        const resp = await fetch(HEALTH_URL, { cache: "no-store" });
        if (resp.ok) {
          const payload = (await resp.json()) as { status?: string };
          next = payload.status === "ok" ? "ok" : "down";
        }
      } catch {
        next = "down";
      }
      if (!cancelled) {
        setState(next);
        setLastCheck(new Date());
      }
    };

    void tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <main className="container">
      <h1>AEO NPUi</h1>
      <section className="pane">
        <h2>Service</h2>
        <div className="indicator-row">
          <span
            className={`dot dot-${state}`}
            aria-label={`service ${state}`}
          />
          <span className="indicator-text">{STATE_TEXT[state]}</span>
        </div>
        <p className="meta">
          {HEALTH_URL}
          {lastCheck !== null && (
            <> &mdash; last check {lastCheck.toLocaleTimeString()}</>
          )}
        </p>
      </section>
    </main>
  );
}

export default App;

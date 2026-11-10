import { useEffect, useState } from "react";

import { getHealth } from "./api";

type Health =
  | { state: "checking" }
  | { state: "ok"; provider: string }
  | { state: "unreachable" };

export function App() {
  const [health, setHealth] = useState<Health>({ state: "checking" });

  useEffect(() => {
    let active = true;
    getHealth()
      .then((h) => {
        if (active) setHealth({ state: "ok", provider: h.llm_provider });
      })
      .catch(() => {
        if (active) setHealth({ state: "unreachable" });
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main
      style={{
        fontFamily: "system-ui, sans-serif",
        maxWidth: 560,
        margin: "64px auto",
        padding: "0 16px",
        lineHeight: 1.5,
      }}
    >
      <h1 style={{ letterSpacing: "-0.02em" }}>Code Snippet Reviewer</h1>
      <p style={{ color: "#555" }}>Scaffold is running. Backend health check:</p>
      <p style={{ fontSize: 18 }}>
        {health.state === "checking" && "Checking backend…"}
        {health.state === "unreachable" && "⚠ Backend unreachable"}
        {health.state === "ok" && (
          <>
            ✓ Backend OK <span style={{ color: "#888" }}>· provider: {health.provider}</span>
          </>
        )}
      </p>
    </main>
  );
}

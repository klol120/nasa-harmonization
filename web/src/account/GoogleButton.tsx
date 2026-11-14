import { useEffect, useRef, useState } from "react";

/** Minimal typing for Google Identity Services (https://accounts.google.com/gsi/client). */
interface GsiId {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: "popup"; auto_select?: boolean }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GsiId } };
  }
}

let gsiLoad: Promise<void> | null = null;
function loadGsi(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  gsiLoad ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      gsiLoad = null;
      reject(new Error("Couldn't load Google sign-in"));
    };
    document.head.appendChild(s);
  });
  return gsiLoad;
}

/** Google's own "Sign in with Google" button. Calls onCredential with the ID token the backend verifies. */
export function GoogleButton({ clientId, onCredential }: { clientId: string; onCredential: (credential: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const cb = useRef(onCredential);
  cb.current = onCredential;
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    loadGsi()
      .then(() => {
        if (!alive || !el.current || !window.google) return;
        window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => cb.current(r.credential), ux_mode: "popup" });
        window.google.accounts.id.renderButton(el.current, { theme: "filled_black", size: "large", shape: "pill", text: "continue_with", width: 280 });
      })
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [clientId]);

  return error ? <p className="warn">{error}</p> : <div ref={el} className="gsi-button" />;
}

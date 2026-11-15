import { useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { GoogleButton } from "./GoogleButton";

/** The one sign-in dialog. Opened with useAuth().requestSignIn(reason). */
export function SignInDialog() {
  const { signInRequest, closeSignIn, config, signInWithGoogle, signInDev } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("demo@wel3a.test");
  const [name, setName] = useState("Demo User");

  useEffect(() => {
    if (!signInRequest) return;
    setError(null);
    const k = (e: KeyboardEvent) => e.key === "Escape" && closeSignIn();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [signInRequest, closeSignIn]);

  if (!signInRequest) return null;

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const google = config?.google_client_id;
  return (
    <div className="modal-scrim" onMouseDown={(e) => e.target === e.currentTarget && closeSignIn()}>
      <div className="modal signin" role="dialog" aria-modal="true" aria-labelledby="signin-title">
        <header className="drawer-head">
          <div>
            <span className="eyebrow">Optional account</span>
            <h2 id="signin-title">Sign in to Wel3a</h2>
          </div>
          <button className="icon-btn" onClick={closeSignIn} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal-body">
          <p className="muted">{signInRequest.reason ?? "Save your areas of interest and get an email when burning there is unusually high."}</p>
          <ul className="signin-perks">
            <li>Save areas and reopen them in one click</li>
            <li>Fire alerts by email for your saved areas</li>
            <li>The monthly burning digest</li>
          </ul>
          <p className="small muted">Everything else (map, calendar, charts, exports) stays open to everyone, signed in or not.</p>

          {google && (
            <div className="signin-google">
              <GoogleButton clientId={google} onCredential={(c) => run(() => signInWithGoogle(c))} />
            </div>
          )}

          {config?.dev_login && (
            <form
              className="signin-dev"
              onSubmit={(e) => {
                e.preventDefault();
                run(() => signInDev(email, name));
              }}
            >
              <span className="eyebrow">Local test sign-in (development only)</span>
              <div className="signin-dev-row">
                <label className="field">
                  <span>Email</span>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </label>
                <label className="field">
                  <span>Name</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} />
                </label>
              </div>
              <button className="btn" disabled={busy}>
                {busy ? "Signing in…" : "Sign in as test user"}
              </button>
            </form>
          )}

          {!google && !config?.dev_login && (
            <p className="warn">{config ? "Sign-in isn't set up on this server yet." : "Can't reach the server right now. Try again in a moment."}</p>
          )}
          {error && <p className="warn">{error}</p>}
          <p className="small muted">
            We only store your email, name and picture from Google. You can delete your account at any time. See the{" "}
            <a href="./privacy.html" target="_blank" rel="noopener">
              privacy policy
            </a>{" "}
            and{" "}
            <a href="./terms.html" target="_blank" rel="noopener">
              terms
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  );
}

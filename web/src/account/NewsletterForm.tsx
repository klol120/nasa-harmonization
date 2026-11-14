import { useState } from "react";
import { useAuth } from "./AuthContext";
import { api } from "./client";

/** Email-list sign-up. Works without an account; signed-in users join with one click. */
export function NewsletterForm({ source, compact }: { source: string; compact?: boolean }) {
  const { me, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "check_email" | "subscribed">("idle");
  const [error, setError] = useState<string | null>(null);

  const status = me?.newsletter.status;
  if (status === "confirmed" || state === "subscribed")
    return <p className={`newsletter-done${compact ? " small" : ""}`}>✓ You're on the email list{me ? ` as ${me.user.email}` : ""}.</p>;
  if (state === "check_email" || status === "pending")
    return <p className={`newsletter-done${compact ? " small" : ""}`}>Check your inbox to confirm your subscription.</p>;

  const submit = async (address: string | null) => {
    setState("busy");
    setError(null);
    try {
      const r = await api.subscribe(address, source);
      setState(r.status);
      if (me) refresh();
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  };

  return (
    <div className={`newsletter${compact ? " is-compact" : ""}`}>
      {!compact && (
        <p className="newsletter-lede">
          <b>Monthly burning digest.</b> One short email a month with each region's newest month, plus project news.
        </p>
      )}
      {me ? (
        <button className="btn btn-primary" disabled={state === "busy"} onClick={() => submit(null)}>
          {state === "busy" ? "Subscribing…" : `Subscribe as ${me.user.email}`}
        </button>
      ) : (
        <form
          className="newsletter-row"
          onSubmit={(e) => {
            e.preventDefault();
            submit(email);
          }}
        >
          <label className="sr-only" htmlFor={`nl-${source}`}>
            Email address
          </label>
          <input id={`nl-${source}`} type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <button className="btn btn-primary" disabled={state === "busy"}>
            {state === "busy" ? "…" : "Subscribe"}
          </button>
        </form>
      )}
      {error && <p className="warn">{error}</p>}
    </div>
  );
}

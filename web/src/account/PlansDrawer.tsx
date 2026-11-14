import { useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { api } from "./client";

interface Plan {
  id: "free" | "pro" | "organization";
  name: string;
  price: string;
  tagline: string;
  features: string[];
}

const PLANS: Plan[] = [
  {
    id: "free",
    name: "Open",
    price: "Free, for everyone",
    tagline: "Everything on this site today. No account needed.",
    features: [
      "Harmonized MODIS + VIIRS calendar, 2000 to today",
      "Map, anomalies, typical year, fire season, fire rings",
      "Any area: presets, boxes, polygons",
      "CSV and PNG exports",
      "With a free account: saved areas, email alerts, monthly digest",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "Coming soon",
    tagline: "For researchers, journalists and consultants.",
    features: [
      "Daily near-real-time updates (about 3 h behind the satellites)",
      "API access with a personal key",
      "PDF area reports for any month or season",
      "Alerts by SMS and WhatsApp",
      "Unlimited saved areas",
    ],
  },
  {
    id: "organization",
    name: "Organisation",
    price: "Talk to us",
    tagline: "For civil defence, municipalities, NGOs and insurers.",
    features: [
      "New regions on request",
      "Shared team workspace and alert routing",
      "Bulk data licensing and integrations",
      "Training and support",
    ],
  },
];

/** Plans page (no payments): Pro and Organisation collect "I'm interested" sign-ups. */
export function PlansDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { me } = useAuth();
  const [picked, setPicked] = useState<"pro" | "organization" | null>(null);
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);

  const submit = async () => {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      await api.planInterest(picked, me ? null : email, org || undefined, message || undefined);
      setSent((s) => [...s, picked]);
      setPicked(null);
      setMessage("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className={`scrim${open ? " is-open" : ""}`} onClick={onClose} aria-hidden />
      <aside className={`drawer plans-drawer${open ? " is-open" : ""}`} aria-hidden={!open} aria-label="Plans">
        <header className="drawer-head">
          <div>
            <span className="eyebrow">Plans</span>
            <h2>Open data first. More for those who need it.</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="drawer-body">
          <p className="muted small">Everything you can see today stays free and open. Paid plans add speed, automation and support on top.</p>
          <div className="plans">
            {PLANS.map((p) => (
              <article key={p.id} className={`plan${p.id === "free" ? " is-current" : ""}`}>
                <header>
                  <h3>{p.name}</h3>
                  <span className="plan-price">{p.price}</span>
                </header>
                <p className="small muted">{p.tagline}</p>
                <ul>
                  {p.features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                {p.id === "free" ? (
                  <span className="plan-badge">Your plan</span>
                ) : sent.includes(p.id) ? (
                  <span className="plan-badge">✓ Thanks, we'll be in touch</span>
                ) : (
                  <button className="btn" onClick={() => setPicked(p.id as "pro" | "organization")}>
                    {p.id === "pro" ? "I'm interested" : "Contact us"}
                  </button>
                )}
              </article>
            ))}
          </div>

          {picked && (
            <form
              className="plan-form"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <h3>{picked === "pro" ? "Tell me when Pro launches" : "Contact us about Organisation"}</h3>
              {!me && (
                <label className="field">
                  <span>Email</span>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </label>
              )}
              {picked === "organization" && (
                <label className="field">
                  <span>Organisation</span>
                  <input value={org} onChange={(e) => setOrg(e.target.value)} />
                </label>
              )}
              <label className="field">
                <span>What would you use it for? (optional)</span>
                <textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
              </label>
              {error && <p className="warn">{error}</p>}
              <div className="plan-form-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setPicked(null)}>
                  Cancel
                </button>
                <button className="btn btn-primary" disabled={busy}>
                  {busy ? "Sending…" : "Send"}
                </button>
              </div>
            </form>
          )}
        </div>
      </aside>
    </>
  );
}

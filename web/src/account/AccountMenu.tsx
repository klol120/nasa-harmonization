import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext";
import { api } from "./client";

function Avatar({ name, picture }: { name: string; picture: string | null }) {
  return picture ? (
    <img className="avatar" src={picture} alt="" width={26} height={26} referrerPolicy="no-referrer" />
  ) : (
    <span className="avatar avatar-initial" aria-hidden>
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

/** Top-bar account control: "Sign in" when signed out, an avatar menu when signed in. */
export function AccountMenu({ onFlash }: { onFlash: (msg: string) => void }) {
  const { me, loading, requestSignIn, signOut, deleteAccount, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  if (loading) return <span className="account-placeholder" aria-hidden />;
  if (!me)
    return (
      <button className="btn btn-ghost" onClick={() => requestSignIn()}>
        Sign in
      </button>
    );

  const u = me.user;
  const name = u.name || u.email;
  const subscribed = me.newsletter.status === "confirmed";
  const act = async (fn: () => Promise<unknown>, done?: string) => {
    try {
      await fn();
      if (done) onFlash(done);
    } catch (e) {
      onFlash((e as Error).message);
    } finally {
      setOpen(false);
    }
  };

  return (
    <div className="menu-wrap" ref={ref}>
      <button className="btn btn-ghost account-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} title={u.email}>
        <Avatar name={name} picture={u.picture} />
        <span className="account-name">{name.split(" ")[0]}</span>
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <b>{name}</b>
            <small>{u.email}</small>
          </div>
          <button role="menuitem" onClick={() => act(async () => document.getElementById("my-areas")?.scrollIntoView({ behavior: "smooth" }))}>
            <b>My areas</b>
            <small>{me.n_areas ? `${me.n_areas} saved · alerts and quick access` : "Save the current area from the sidebar"}</small>
          </button>
          <button
            role="menuitem"
            onClick={() => act(async () => (await api.setNewsletter(!subscribed), await refresh()), subscribed ? "Unsubscribed from the digest" : "Subscribed to the digest")}
          >
            <b>{subscribed ? "Unsubscribe from the digest" : "Get the monthly digest"}</b>
            <small>{subscribed ? "You get one email a month" : "One short email a month, no spam"}</small>
          </button>
          {u.is_admin && (
            <button role="menuitem" onClick={() => act(async () => setStats(await api.adminStats()))}>
              <b>Admin stats</b>
              <small>Users, subscribers, saved areas, emails</small>
            </button>
          )}
          <button role="menuitem" onClick={() => act(signOut, "Signed out")}>
            <b>Sign out</b>
          </button>
          <button
            role="menuitem"
            className="menu-danger"
            onClick={() =>
              window.confirm("Delete your account, saved areas and alerts? This can't be undone.") && act(deleteAccount, "Account deleted")
            }
          >
            <b>Delete account</b>
            <small>Removes your saved areas and takes you off the email list</small>
          </button>
        </div>
      )}
      {stats && (
        <div className="modal-scrim" onMouseDown={(e) => e.target === e.currentTarget && setStats(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Admin stats">
            <header className="drawer-head">
              <div>
                <span className="eyebrow">Admin</span>
                <h2>Business at a glance</h2>
              </div>
              <button className="icon-btn" onClick={() => setStats(null)} aria-label="Close">
                ✕
              </button>
            </header>
            <div className="modal-body">
              <pre className="stats-pre">{JSON.stringify(stats, null, 2)}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

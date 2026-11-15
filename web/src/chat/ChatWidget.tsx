import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { type ChatConfig, ChatError, type ChatTurn, getChatConfig, streamChat } from "./client";
import { Markdown } from "./Markdown";

interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Assistant only: the answer is still arriving. */
  streaming?: boolean;
  /** Assistant only: why the answer failed (the message is not sent back to the model). */
  error?: string;
  /** Assistant only: stopped by the person, or cut by the length limit. */
  cut?: "stopped" | "length";
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Snapshot of the view, read when a question is sent so the answer matches the screen. */
  getContext: () => unknown;
  /** What the assistant can see right now, e.g. "Lebanon · Aug 2021". */
  scope: string;
  suggestions: string[];
}

const STORE_KEY = "wel3a.chat";
const MAX_INPUT = 4000;

const uid = () => Math.random().toString(36).slice(2, 10);

function restore(): Msg[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE_KEY) ?? "[]") as Msg[];
    return Array.isArray(saved) ? saved.filter((m) => m && typeof m.content === "string" && (m.role === "user" || m.role === "assistant")) : [];
  } catch {
    return [];
  }
}

/** The turns the model should see: everything said, without failed or empty answers. */
const turns = (msgs: Msg[]): ChatTurn[] => msgs.filter((m) => !m.error && m.content.trim()).map((m) => ({ role: m.role, content: m.content }));

/** The assistant: a launcher in the corner that opens a chat panel over any page. */
export function ChatWidget({ open, onOpenChange, getContext, scope, suggestions }: Props) {
  const [messages, setMessages] = useState<Msg[]>(restore);
  const [input, setInput] = useState("");
  const [config, setConfig] = useState<ChatConfig | null>(null);
  const busy = messages.some((m) => m.streaming);

  const abort = useRef<AbortController | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const stick = useRef(true); // keep the newest text in view unless the person scrolled up
  const wasOpen = useRef(open);

  // Whether the server has a key. If the check itself fails, sending still works and reports why.
  useEffect(() => {
    if (!open || config) return;
    const ctl = new AbortController();
    getChatConfig(ctl.signal)
      .then(setConfig)
      .catch(() => undefined);
    return () => ctl.abort();
  }, [open, config]);

  useEffect(() => {
    try {
      // An answer in progress is saved as it stands, so a reload doesn't show it as still arriving.
      sessionStorage.setItem(STORE_KEY, JSON.stringify(messages.slice(-60).map((m) => (m.streaming ? { ...m, streaming: false, cut: "stopped" } : m))));
    } catch {
      // storage blocked: the conversation lasts until the page is closed
    }
  }, [messages]);

  useEffect(() => () => abort.current?.abort(), []);

  // Focus moves into the panel when it opens and back to the launcher when it closes.
  useEffect(() => {
    if (open) box.current?.focus({ preventScroll: true });
    else if (wasOpen.current) launcher.current?.focus({ preventScroll: true });
    wasOpen.current = open;
  }, [open]);

  useLayoutEffect(() => {
    const el = list.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages, open]);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(132, el.scrollHeight)}px`;
    el.style.overflowY = el.scrollHeight > 132 ? "auto" : "hidden"; // a scrollbar only once it stops growing
  }, [input, open]);

  /** Asks for an answer to `history`, which ends with the person's question. */
  const answer = useCallback(
    async (history: Msg[]) => {
      const id = uid();
      const ctl = new AbortController();
      abort.current = ctl;
      stick.current = true;
      setMessages([...history, { id, role: "assistant", content: "", streaming: true }]);
      const patch = (fn: (m: Msg) => Msg) => setMessages((cur) => cur.map((m) => (m.id === id ? fn(m) : m)));
      try {
        const { truncated } = await streamChat({
          messages: turns(history),
          context: getContext(),
          signal: ctl.signal,
          onText: (t) => patch((m) => ({ ...m, content: m.content + t })),
        });
        patch((m) => ({ ...m, streaming: false, cut: truncated ? "length" : undefined }));
      } catch (e) {
        if ((e as Error).name === "AbortError") patch((m) => ({ ...m, streaming: false, cut: "stopped" }));
        else patch((m) => ({ ...m, streaming: false, error: e instanceof ChatError ? e.message : "Something went wrong. Try again." }));
      } finally {
        if (abort.current === ctl) abort.current = null;
      }
    },
    [getContext],
  );

  const send = (text: string) => {
    const q = text.trim().slice(0, MAX_INPUT);
    if (!q || busy || disabled) return;
    setInput("");
    void answer([...messages, { id: uid(), role: "user", content: q }]);
  };

  /** Drops the failed answer and asks again with the same conversation. */
  const retry = (failed: Msg) => {
    if (busy) return;
    const history = messages.slice(0, messages.indexOf(failed));
    if (history.at(-1)?.role === "user") void answer(history);
  };

  const reset = () => {
    abort.current?.abort();
    setMessages([]);
    setInput("");
    box.current?.focus();
  };

  const disabled = config?.enabled === false;
  const empty = messages.length === 0;

  return (
    <>
      {open && (
        <section
          className="chat-panel"
          role="dialog"
          aria-label="Ask Phoenical"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              onOpenChange(false);
            }
          }}
        >
          <header className="chat-head">
            <img className="chat-avatar" src="./emblem.png" alt="" width={32} height={32} />
            <div className="chat-title">
              <b>Ask Phoenical</b>
              <span title={`The assistant answers from the figures on screen: ${scope}`}>
                <i className="chat-dot" aria-hidden /> Looking at {scope}
              </span>
            </div>
            {!empty && (
              <button className="icon-btn" onClick={reset} aria-label="New chat" title="New chat">
                <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden>
                  <path d="M10.5 3.5H5.2A1.7 1.7 0 0 0 3.5 5.2v9.6a1.7 1.7 0 0 0 1.7 1.7h9.6a1.7 1.7 0 0 0 1.7-1.7V9.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  <path d="m9 11 .5-2.6 6-6a1.5 1.5 0 0 1 2.1 2.1l-6 6L9 11Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                </svg>
              </button>
            )}
            <button className="icon-btn" onClick={() => onOpenChange(false)} aria-label="Close the assistant" title="Close (Esc)">
              <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden>
                <path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </button>
          </header>

          <div
            className="chat-list"
            ref={list}
            role="log"
            aria-live="polite"
            aria-busy={busy}
            onScroll={(e) => {
              const el = e.currentTarget;
              stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
            }}
          >
            {empty ? (
              <div className="chat-empty">
                <h3>What would you like to know?</h3>
                <p>
                  Ask about the fire record on screen, what a figure means, or how to do something in the app. Answers use the numbers you are looking at.
                </p>
                {disabled ? (
                  <p className="chat-setup">
                    <b>The assistant isn't set up yet.</b> Add <code>OPENROUTER_API_KEY</code> (free) to the server's <code>.env</code> and restart the API.
                  </p>
                ) : (
                  <div className="chat-suggest">
                    {suggestions.map((s) => (
                      <button key={s} onClick={() => send(s)}>
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="chat-msg is-user">
                    {m.content}
                  </div>
                ) : (
                  <div key={m.id} className={`chat-msg is-bot${m.error ? " is-error" : ""}`}>
                    {m.content ? (
                      <Markdown text={m.content} />
                    ) : m.streaming ? (
                      <span className="chat-typing" role="status" aria-label="Thinking">
                        <i />
                        <i />
                        <i />
                      </span>
                    ) : null}
                    {m.streaming && m.content && <span className="chat-caret" aria-hidden />}
                    {m.cut && <p className="chat-note">{m.cut === "length" ? "The answer reached its length limit. Ask for the rest." : m.content ? "Stopped." : "Stopped before answering."}</p>}
                    {m.error && (
                      <p className="chat-error" role="alert">
                        {m.error}{" "}
                        <button className="link" onClick={() => retry(m)} disabled={busy}>
                          Try again
                        </button>
                      </p>
                    )}
                  </div>
                ),
              )
            )}
          </div>

          <form
            className="chat-form"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <div className="chat-field">
              <textarea
                ref={box}
                rows={1}
                value={input}
                maxLength={MAX_INPUT}
                disabled={disabled}
                placeholder={disabled ? "The assistant isn't set up yet" : "Ask about this fire record"}
                aria-label="Your question"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  // Enter sends; Shift+Enter is a new line. Not while an input method is composing.
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send(input);
                  }
                }}
              />
              {busy ? (
                <button type="button" className="chat-send is-stop" onClick={() => abort.current?.abort()} aria-label="Stop answering" title="Stop">
                  <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden>
                    <rect x="4.5" y="4.5" width="11" height="11" rx="2.5" fill="currentColor" />
                  </svg>
                </button>
              ) : (
                <button type="submit" className="chat-send" disabled={!input.trim() || disabled} aria-label="Send" title="Send (Enter)">
                  <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden>
                    <path d="M10 15.5v-11M5.2 9.2 10 4.4l4.8 4.8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              )}
            </div>
            <p className="chat-foot">AI answers can be wrong. Check key figures against the charts, and don't rely on this for safety decisions.</p>
          </form>
        </section>
      )}

      <button
        ref={launcher}
        className={`chat-launcher${open ? " is-open" : ""}`}
        onClick={() => onOpenChange(!open)}
        aria-label={open ? "Close the assistant" : "Ask Phoenical, the assistant"}
        aria-expanded={open}
        title={open ? "Close" : "Ask Phoenical"}
      >
        {open ? (
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
            <path d="m6.5 9.5 5.5 5.5 5.5-5.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden>
            <path
              d="M12 3.5c-5 0-9 3.5-9 7.9 0 2.4 1.2 4.500 3.100 6l-.7 3.300 3.800-1.800c.9.2 1.800.4 2.800.4 5 0 9-3.500 9-7.900s-4-7.900-9-7.900Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <path d="m12 7.600.9 2.500 2.500.9-2.500.9-.9 2.500-.9-2.500-2.500-.9 2.500-.9.9-2.500Z" fill="currentColor" />
          </svg>
        )}
      </button>
    </>
  );
}

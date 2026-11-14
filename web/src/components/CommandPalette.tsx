import { useEffect, useMemo, useRef, useState } from "react";

export interface Command {
  id: string;
  group: string;
  label: string;
  /** Short note on the right (current value, shortcut…). */
  hint?: string;
  /** Extra words that should find this command. */
  keywords?: string;
  /** Only listed once the person types (long lists such as years). */
  searchOnly?: boolean;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}

export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const MOD_KEY = isMac ? "⌘" : "Ctrl";

/** Spotlight-style search over pages, places, years and actions. */
export function CommandPalette({ open, onClose, commands }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  const results = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return commands.filter((c) => !c.searchOnly);
    return commands
      .filter((c) => {
        const text = `${c.label} ${c.group} ${c.keywords ?? ""}`.toLowerCase();
        return words.every((w) => text.includes(w));
      })
      .sort((a, b) => Number(!a.label.toLowerCase().startsWith(words[0])) - Number(!b.label.toLowerCase().startsWith(words[0])))
      .slice(0, 50);
  }, [commands, query]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    list.current?.querySelector(`[data-k="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const run = (c: Command | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };

  // Results grouped in the order the groups first appear.
  const groups: { name: string; items: { c: Command; k: number }[] }[] = [];
  results.forEach((c, k) => {
    let g = groups.find((x) => x.name === c.group);
    if (!g) groups.push((g = { name: c.group, items: [] }));
    g.items.push({ c, k });
  });

  return (
    <div className="palette-scrim" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search" onMouseDown={(e) => e.stopPropagation()}>
        <div className="palette-search">
          <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden>
            <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
            <path d="M13.2 13.2 17 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          </svg>
          <input
            ref={input}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages, places, years and actions"
            aria-label="Search pages, places, years and actions"
            aria-controls="palette-list"
            aria-activedescendant={results.length ? `pc-${active}` : undefined}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(results.length - 1, a + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(0, a - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(results[active]);
              } else if (e.key === "Escape") {
                e.preventDefault();
                onClose();
              }
            }}
          />
          <kbd>Esc</kbd>
        </div>

        <div className="palette-list" id="palette-list" role="listbox" ref={list}>
          {groups.length ? (
            groups.map((g) => (
              <div key={g.name} className="palette-group" role="group" aria-label={g.name}>
                <span className="palette-group-name">{g.name}</span>
                {g.items.map(({ c, k }) => (
                  <button
                    key={c.id}
                    id={`pc-${k}`}
                    data-k={k}
                    role="option"
                    aria-selected={k === active}
                    className={`palette-item${k === active ? " is-active" : ""}`}
                    onMouseMove={() => setActive(k)}
                    onClick={() => run(c)}
                  >
                    <span>{c.label}</span>
                    {c.hint && <small>{c.hint}</small>}
                  </button>
                ))}
              </div>
            ))
          ) : (
            <p className="palette-empty">Nothing matches “{query}”. Try a page, a place or a year.</p>
          )}
        </div>

        <footer className="palette-foot">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> to choose, <kbd>↵</kbd> to open
          </span>
          <span>
            <kbd>←</kbd>
            <kbd>→</kbd> month · <kbd>⇧</kbd>+<kbd>←</kbd>
            <kbd>→</kbd> year · <kbd>{MOD_KEY}</kbd>
            <kbd>B</kbd> sidebar
          </span>
        </footer>
      </div>
    </div>
  );
}

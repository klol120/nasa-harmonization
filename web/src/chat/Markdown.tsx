import { Fragment, type ReactNode } from "react";

/**
 * The small subset of Markdown the assistant writes: paragraphs, bullet and numbered lists,
 * **bold**, *italic*, `code`, fenced code and links. Built as React elements, never as HTML,
 * so nothing the model writes can inject markup.
 */

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+?\*\*|\*[^*\s][^*\n]*?\*|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, k) => {
    if (!part) return null;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={k}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={k}>{inline(part.slice(2, -2))}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={k}>{part.slice(1, -1)}</em>;
    const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(part);
    if (link)
      return (
        <a key={k} href={link[2]} target="_blank" rel="noopener noreferrer">
          {link[1]}
        </a>
      );
    return <Fragment key={k}>{part}</Fragment>;
  });
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul" | "ol"; items: string[] } | { kind: "pre"; text: string };

function blocks(src: string): Block[] {
  const out: Block[] = [];
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  for (let k = 0; k < lines.length; k++) {
    const line = lines[k];
    if (line.trimStart().startsWith("```")) {
      const body: string[] = [];
      for (k++; k < lines.length && !lines[k].trimStart().startsWith("```"); k++) body.push(lines[k]);
      out.push({ kind: "pre", text: body.join("\n") });
      continue;
    }
    if (!line.trim()) {
      // A blank line ends a paragraph; lists continue across blank lines between items.
      if (out.at(-1)?.kind === "p") out.push({ kind: "p", lines: [] });
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const last = out.at(-1);
    if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      const text = (bullet ?? numbered)![1];
      if (last?.kind === kind) last.items.push(text);
      else out.push({ kind, items: [text] });
    } else if ((last?.kind === "ul" || last?.kind === "ol") && /^\s{2,}\S/.test(line)) {
      last.items[last.items.length - 1] += ` ${line.trim()}`; // wrapped list item
    } else {
      // Headings are not asked for; if one arrives it reads as a bold line.
      const heading = /^#{1,6}\s+(.*)$/.exec(line);
      const text = heading ? `**${heading[1].replace(/\*\*/g, "")}**` : line;
      if (last?.kind === "p" && !heading) last.lines.push(text);
      else out.push({ kind: "p", lines: [text] });
      if (heading) out.push({ kind: "p", lines: [] });
    }
  }
  return out.filter((b) => b.kind !== "p" || b.lines.length);
}

export function Markdown({ text }: { text: string }) {
  return (
    <>
      {blocks(text).map((b, k) =>
        b.kind === "pre" ? (
          <pre key={k}>{b.text}</pre>
        ) : b.kind === "p" ? (
          <p key={k}>
            {b.lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l)}
              </Fragment>
            ))}
          </p>
        ) : b.kind === "ul" ? (
          <ul key={k}>
            {b.items.map((it, j) => (
              <li key={j}>{inline(it)}</li>
            ))}
          </ul>
        ) : (
          <ol key={k}>
            {b.items.map((it, j) => (
              <li key={j}>{inline(it)}</li>
            ))}
          </ol>
        ),
      )}
    </>
  );
}

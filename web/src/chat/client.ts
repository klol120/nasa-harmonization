import { API_URL } from "../config";

/** Client for the assistant (backend/firecal_api/chat.py). The API key never leaves the server. */

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatConfig {
  enabled: boolean;
  model: string;
}

export class ChatError extends Error {}

export async function getChatConfig(signal?: AbortSignal): Promise<ChatConfig> {
  const res = await fetch(`${API_URL}/chat/config`, { signal });
  if (!res.ok) throw new ChatError(`Request failed (${res.status})`);
  return res.json();
}

/** The server accepts at most this many turns; older ones are left out of the request. */
const MAX_TURNS = 30;

/**
 * Sends the conversation and calls `onText` with each piece of the answer as it arrives.
 * Resolves when the answer is complete; `truncated` means it hit the length limit.
 */
export async function streamChat(opts: { messages: ChatTurn[]; context: unknown; signal: AbortSignal; onText: (text: string) => void }): Promise<{ truncated: boolean }> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ messages: opts.messages.slice(-MAX_TURNS), context: opts.context }),
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ChatError("Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok || !res.body) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      // not JSON
    }
    throw new ChatError(typeof detail === "string" ? detail : res.status === 404 ? "This server doesn't have the assistant yet. Update and restart the API." : `The assistant is unavailable (${res.status}).`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: { truncated: boolean } | null = null;

  const handle = (block: string) => {
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    const payload = JSON.parse(data) as { text?: string; message?: string; truncated?: boolean };
    if (event === "delta" && payload.text) opts.onText(payload.text);
    else if (event === "done") result = { truncated: !!payload.truncated };
    else if (event === "error") throw new ChatError(payload.message ?? "Something went wrong. Try again.");
  };

  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done }).replace(/\r\n/g, "\n");
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      handle(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
    }
    if (done) break;
  }
  if (!result) throw new ChatError("The answer was cut off. Try again.");
  return result;
}

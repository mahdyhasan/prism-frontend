"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  MessageSquare,
  Plus,
  Send,
} from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";
import {
  chatApi,
  streamChatMessage,
  type ChatMessageResponse,
  type ChatSessionResponse,
} from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

type SourceScope = "all" | "ga4" | "gsc";

interface ToolCallBubble {
  kind: "tool_call";
  toolName: string;
  inputSummary?: string;
  rowCount?: number;
  expanded: boolean;
}

interface TextBubble {
  kind: "text";
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

type ChatBubble = TextBubble | ToolCallBubble;

// ── Confidence chip parser ────────────────────────────────────────────────────

const CONFIDENCE_LABEL_STYLES: Record<string, string> = {
  "[high]": "text-green-400 bg-green-950/50",
  "[medium]": "text-yellow-400 bg-yellow-950/50",
  "[hypothesis]": "text-purple-400 bg-purple-950/50",
  "[speculation]": "text-slate-400 bg-slate-800",
  "[insufficient_data]": "text-slate-500 bg-slate-800",
};

function parseConfidenceChips(text: string): React.ReactNode {
  const parts = text.split(
    /(\[high\]|\[medium\]|\[hypothesis\]|\[speculation\]|\[insufficient_data\])/g,
  );
  return parts.map((part, i) => {
    const cls = CONFIDENCE_LABEL_STYLES[part];
    if (cls) {
      return (
        <span
          key={i}
          className={`inline-block rounded px-1 py-0.5 text-[10px] font-semibold ${cls} mx-0.5`}
        >
          {part}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

// ── Reframe detection ─────────────────────────────────────────────────────────

function isReframing(content: string): boolean {
  return content.trimStart().startsWith("## Reframing");
}

// ── Relative time ─────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ── Quick prompts ─────────────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  "What changed last week",
  "Top opportunities",
  "Where am I leaving money",
  "Argue against my current SEO focus",
];

// ── Source scope tabs ─────────────────────────────────────────────────────────

const SCOPE_OPTIONS: { value: SourceScope; label: string; disabled?: boolean }[] = [
  { value: "all", label: "All" },
  { value: "ga4", label: "GA4" },
  { value: "gsc", label: "GSC" },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const searchParams = useSearchParams();
  const propertyId = Number(searchParams.get("property_id") ?? 0);
  const initialPrompt = searchParams.get("prompt") ?? "";

  const queryClient = useQueryClient();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);

  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [bubbles, setBubbles] = useState<ChatBubble[]>([]);
  const [input, setInput] = useState(initialPrompt);
  const [streaming, setStreaming] = useState(false);
  const [scope, setScope] = useState<SourceScope>("all");

  // Sessions list
  const sessionsQuery = useQuery({
    queryKey: ["chat-sessions", propertyId],
    queryFn: () => chatApi.listSessions(propertyId),
    enabled: !!propertyId,
    staleTime: 30_000,
  });

  const sessions = (sessionsQuery.data ?? []).slice().sort(
    (a, b) =>
      new Date(b.last_message_at).getTime() - new Date(a.last_message_at).getTime(),
  );

  // Load session
  const loadSession = useCallback(async (sessionId: number) => {
    const session = await chatApi.getSession(sessionId);
    setActiveSessionId(session.id);
    const loaded: ChatBubble[] = (session.messages ?? []).map((m: ChatMessageResponse) => ({
      kind: "text" as const,
      role: m.role,
      content: m.content,
    }));
    setBubbles(loaded);
  }, []);

  // Scroll to bottom whenever bubbles change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles]);

  // Cleanup stream on unmount
  useEffect(() => {
    return () => {
      stopStreamRef.current?.();
    };
  }, []);

  // Send message
  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;

      let sessionId = activeSessionId;

      // Create session if needed
      if (!sessionId) {
        const session = await chatApi.createSession({
          property_id: propertyId,
          source_scope: scope,
        });
        sessionId = session.id;
        setActiveSessionId(session.id);
        void queryClient.invalidateQueries({ queryKey: ["chat-sessions", propertyId] });
      }

      // Add user bubble
      setBubbles((prev) => [
        ...prev,
        { kind: "text", role: "user", content: text },
      ]);
      setInput("");
      setStreaming(true);

      // Placeholder assistant bubble
      setBubbles((prev) => [
        ...prev,
        { kind: "text", role: "assistant", content: "", streaming: true },
      ]);

      let assistantContent = "";
      let currentToolIdx: number | null = null;

      const stop = streamChatMessage(sessionId, text, scope, (event) => {
        if (event.type === "text_delta") {
          assistantContent += String(event.delta ?? "");
          setBubbles((prev) => {
            const next = [...prev];
            // Find the streaming assistant bubble (last one)
            const lastIdx = next.length - 1;
            if (next[lastIdx]?.kind === "text" && (next[lastIdx] as TextBubble).role === "assistant") {
              next[lastIdx] = {
                kind: "text",
                role: "assistant",
                content: assistantContent,
                streaming: true,
              };
            }
            return next;
          });
        } else if (event.type === "tool_start") {
          const toolBubble: ToolCallBubble = {
            kind: "tool_call",
            toolName: String(event.tool_name ?? "query"),
            inputSummary: event.input_summary ? String(event.input_summary) : undefined,
            expanded: false,
          };
          setBubbles((prev) => {
            // Insert tool bubble before the streaming assistant bubble
            const next = [...prev];
            const lastIdx = next.length - 1;
            next.splice(lastIdx, 0, toolBubble);
            currentToolIdx = lastIdx;
            return next;
          });
        } else if (event.type === "tool_result") {
          setBubbles((prev) => {
            if (currentToolIdx === null) return prev;
            const next = [...prev];
            const bubble = next[currentToolIdx];
            if (bubble?.kind === "tool_call") {
              next[currentToolIdx] = {
                ...bubble,
                rowCount: typeof event.row_count === "number" ? event.row_count : undefined,
              };
            }
            return next;
          });
        } else if (event.type === "done") {
          setBubbles((prev) => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            if (next[lastIdx]?.kind === "text") {
              next[lastIdx] = {
                kind: "text",
                role: "assistant",
                content: assistantContent,
                streaming: false,
              };
            }
            return next;
          });
          setStreaming(false);
          stopStreamRef.current = null;
          void queryClient.invalidateQueries({ queryKey: ["chat-sessions", propertyId] });
        } else if (event.type === "error") {
          setBubbles((prev) => {
            const next = [...prev];
            const lastIdx = next.length - 1;
            if (next[lastIdx]?.kind === "text") {
              next[lastIdx] = {
                kind: "text",
                role: "assistant",
                content: `_Error: ${String(event.message)}_`,
                streaming: false,
              };
            }
            return next;
          });
          setStreaming(false);
          stopStreamRef.current = null;
        }
      });

      stopStreamRef.current = stop;
    },
    [activeSessionId, bubbles.length, propertyId, queryClient, scope, streaming],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void sendMessage(input);
      }
    },
    [input, sendMessage],
  );

  const toggleToolBubble = useCallback((idx: number) => {
    setBubbles((prev) => {
      const next = [...prev];
      const bubble = next[idx];
      if (bubble?.kind === "tool_call") {
        next[idx] = { ...bubble, expanded: !bubble.expanded };
      }
      return next;
    });
  }, []);

  if (!propertyId) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <p className="text-sm text-slate-400">
          Select a property from the sidebar to start chatting.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar propertyId={propertyId} />

      {/* Sessions sidebar */}
      <aside className="flex w-[280px] flex-col border-r border-slate-800 bg-slate-950">
        <div className="flex h-14 items-center justify-between border-b border-slate-800 px-4">
          <span className="text-sm font-semibold text-white">Conversations</span>
          <button
            type="button"
            onClick={() => {
              setActiveSessionId(null);
              setBubbles([]);
            }}
            title="New chat"
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-700 text-slate-400 hover:border-slate-600 hover:text-white transition"
          >
            <Plus size={14} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {sessionsQuery.isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={16} className="animate-spin text-slate-600" />
            </div>
          )}
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              onClick={() => void loadSession(session.id)}
              className={clsx(
                "mb-0.5 w-full rounded-lg px-3 py-2 text-left transition",
                activeSessionId === session.id
                  ? "bg-slate-800"
                  : "hover:bg-slate-900",
              )}
            >
              <p className="truncate text-xs font-medium text-white">
                {session.title ?? "New conversation"}
              </p>
              <p className="text-[10px] text-slate-500">
                {relativeTime(session.last_message_at)}
              </p>
            </button>
          ))}
          {!sessionsQuery.isLoading && sessions.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-slate-600">
              No conversations yet
            </p>
          )}
        </div>
      </aside>

      {/* Chat column */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Source scope chips */}
        <div className="flex h-14 items-center gap-2 border-b border-slate-800 px-4">
          {SCOPE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setScope(value)}
              className={clsx(
                "rounded-lg px-3 py-1.5 text-xs font-semibold transition",
                scope === value
                  ? "bg-brand-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:text-white",
              )}
            >
              {label}
            </button>
          ))}
          <span className="ml-auto rounded-lg bg-slate-800/50 px-2 py-1 text-[10px] text-slate-600">
            Ads — coming soon
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {/* Quick prompts — shown when conversation is empty */}
          {bubbles.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-800/60 text-brand-500">
                <MessageSquare size={22} />
              </div>
              <p className="text-sm text-slate-400">Ask anything about your data</p>
              <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => void sendMessage(prompt)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-600 hover:text-white transition"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Bubble list */}
          <div className="space-y-4 pb-2">
            {bubbles.map((bubble, idx) => {
              if (bubble.kind === "tool_call") {
                return (
                  <ToolCallBubbleView
                    key={idx}
                    bubble={bubble}
                    onToggle={() => toggleToolBubble(idx)}
                  />
                );
              }
              if (bubble.role === "user") {
                return (
                  <div key={idx} className="flex justify-end">
                    <div className="max-w-lg rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white">
                      {bubble.content}
                    </div>
                  </div>
                );
              }
              // Assistant bubble
              const reframe = isReframing(bubble.content);
              return (
                <div
                  key={idx}
                  className={clsx(
                    "rounded-2xl border px-5 py-4 text-sm leading-relaxed text-slate-200",
                    reframe
                      ? "border-amber-800/50 bg-amber-950/20"
                      : "border-slate-800 bg-slate-900",
                  )}
                >
                  <div className="whitespace-pre-wrap break-words">
                    {parseConfidenceChips(bubble.content)}
                  </div>
                  {bubble.streaming && (
                    <span className="ml-1 inline-block h-3.5 w-0.5 animate-pulse bg-brand-400" />
                  )}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input bar */}
        <div className="border-t border-slate-800 p-4">
          <div className="flex items-end gap-3 rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 focus-within:border-slate-600 transition">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={streaming}
              placeholder="Ask a question about your data…"
              rows={1}
              className="flex-1 resize-none bg-transparent text-sm text-white placeholder:text-slate-600 focus:outline-none disabled:opacity-50"
              style={{ maxHeight: "96px", overflowY: "auto" }}
            />
            {streaming ? (
              <div className="flex flex-shrink-0 items-center gap-1.5 text-xs text-slate-500">
                <Loader2 size={14} className="animate-spin" />
                Thinking…
              </div>
            ) : (
              <button
                type="button"
                onClick={() => void sendMessage(input)}
                disabled={!input.trim() || streaming}
                className="flex-shrink-0 rounded-lg bg-brand-600 p-2 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Send size={14} />
              </button>
            )}
          </div>
          <p className="mt-1.5 text-center text-[10px] text-slate-700">
            Enter to send &middot; Shift+Enter for newline
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Tool call bubble ──────────────────────────────────────────────────────────

function ToolCallBubbleView({
  bubble,
  onToggle,
}: {
  bubble: ToolCallBubble;
  onToggle: () => void;
}) {
  return (
    <div className="flex justify-start">
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex items-center gap-2 rounded-full border border-slate-700/60 bg-slate-800/60 px-3 py-1 text-xs text-slate-400 hover:text-white transition"
      >
        {bubble.expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <span className="font-mono">{bubble.toolName}</span>
        {bubble.rowCount !== undefined && (
          <span className="text-slate-600">— {bubble.rowCount} rows</span>
        )}
      </button>
      {bubble.expanded && bubble.inputSummary && (
        <div className="ml-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-500">
          {bubble.inputSummary}
        </div>
      )}
    </div>
  );
}

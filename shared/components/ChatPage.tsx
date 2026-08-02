"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ToolCard from "./ToolCard";
import TypingIndicator from "./TypingIndicator";
import type { ChatRequest, ChatResponse, ToolOutput } from "@/types/chat";

interface Message {
  role: "user" | "assistant";
  content: string;
  toolOutputs?: ToolOutput[];
}

export default function ChatPage({ frameworkName }: { frameworkName: string }) {
  const [dark, setDark] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, [messages.length]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setInput("");
    const userMessage: Message = { role: "user", content: trimmed };
    const prevMessages = [...messages, userMessage];
    setMessages(prevMessages);
    setLoading(true);

    try {
      const fetchStart = Date.now();
      console.log(`[frontend] fetch started at ${new Date().toISOString()}`);
      
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: prevMessages } satisfies ChatRequest),
        signal: AbortSignal.timeout(300000),
      });
      
      const fetchElapsed = Date.now() - fetchStart;
      console.log(`[frontend] response received in ${fetchElapsed}ms`);

      const data: ChatResponse = await res.json();

      if (res.ok) {
        setMessages(prev => [
          ...prev,
          {
            role: "assistant",
            content: data.text ?? "",
            toolOutputs: data.toolOutputs,
          },
        ]);
      } else {
        setMessages(prev => [
          ...prev,
          { role: "assistant", content: data.error ?? "Unknown error" },
        ]);
      }
    } catch {
      setMessages(prev => [
        ...prev,
        { role: "assistant", content: "Failed to connect to backend" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Page background (outer layer) — gives the chat card visual depth
  const pageBg = dark ? "bg-zinc-950" : "bg-zinc-200";
  // Chat card background (inner layer) — the actual chat surface
  const cardBg = dark ? "bg-zinc-900" : "bg-white";
  // Card border
  const cardBorder = dark ? "border-zinc-800" : "border-zinc-300";
  // Input bar background
  const inputBarBg = dark ? "bg-zinc-900" : "bg-zinc-50";
  // Input field background
  const inputFieldBg = dark ? "bg-zinc-800" : "bg-zinc-100";
  // Text colors
  const textPrimary = dark ? "text-zinc-100" : "text-zinc-900";
  const textMuted = dark ? "text-zinc-500" : "text-zinc-400";
  // Message bubble colors
  const userBubble = "bg-blue-600 text-white";
  const assistantBubble = dark ? "bg-zinc-800 text-zinc-100" : "bg-zinc-100 text-zinc-900";

  return (
    <div className={`min-h-screen ${pageBg} flex flex-col items-center justify-center p-4 sm:p-6`}>
      {/* Chat card */}
      <div className={`w-full max-w-2xl h-[min(100dvh-2rem,42rem)] flex flex-col ${cardBg} border ${cardBorder} rounded-2xl shadow-xl overflow-hidden`}>
        {/* Header */}
        <header className={`flex items-center justify-between px-5 py-3 border-b ${cardBorder}`}>
          <h1 className={`text-sm font-semibold tracking-tight ${textPrimary}`}>Chat</h1>
          <button
            onClick={() => setDark(d => !d)}
            className={`text-xs px-2.5 py-1.5 rounded-full ${inputFieldBg} ${textMuted} hover:opacity-80 transition-opacity`}
            aria-label="Toggle theme"
          >
            {dark ? "Light" : "Dark"}
          </button>
        </header>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-5 py-5">
          {messages.length === 0 && (
            <div className={`flex flex-col items-center justify-center h-full ${textMuted} text-sm`}>
              <p>No messages yet</p>
              <p className="text-xs mt-1">Send a message to start chatting</p>
            </div>
          )}

          <div className="space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className={`${msg.role === "user" ? "text-right" : "text-left"}`}>
                <div
                  className={`inline-block max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
                    msg.role === "user" ? userBubble : assistantBubble
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>
                {msg.toolOutputs && msg.toolOutputs.length > 0 && (
                  <div className={`mt-2 space-y-2 ${msg.role === "user" ? "max-w-[85%] ml-auto" : ""}`}>
                    {msg.toolOutputs.map((out, j) => (
                      <ToolCard key={j} output={out} dark={dark} />
                    ))}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex items-center gap-2 text-sm">
                <TypingIndicator dark={dark} />
                <span className={textMuted}>thinking...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input bar */}
        <div className={`border-t ${cardBorder} ${inputBarBg} px-4 py-3`}>
          <form
            onSubmit={e => {
              e.preventDefault();
              send();
            }}
          >
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Type a message..."
                className={`flex-1 px-3.5 py-2.5 rounded-lg text-sm ${inputFieldBg} ${textPrimary} placeholder:text-zinc-500 outline-none border border-transparent focus:border-blue-600 transition-colors`}
                disabled={loading}
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="px-4 py-2.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Send
              </button>
            </div>
          </form>
          <p className={`text-center text-xs mt-2 ${textMuted}`}>
            Chatlet powered by {frameworkName}
          </p>
        </div>
      </div>
    </div>
  );
}

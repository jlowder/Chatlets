"use client";

import { useState, useRef, useEffect } from "react";
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

  const scrollIntoView = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollIntoView, [messages, loading]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: userMsg } satisfies ChatRequest),
      });
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

  const bg = dark ? "bg-zinc-950" : "bg-white";
  const textPrimary = dark ? "text-zinc-100" : "text-zinc-900";
  const textMuted = dark ? "text-zinc-400" : "text-zinc-500";
  const inputBg = dark ? "bg-zinc-900" : "bg-zinc-100";
  const borderSubtle = dark ? "border-zinc-800" : "border-zinc-200";

  return (
    <div className={`min-h-screen ${bg} ${textPrimary} flex flex-col`}>
      {/* Header */}
      <header className={`flex items-center justify-between px-4 py-3 border-b ${borderSubtle}`}>
        <h1 className="text-sm font-semibold tracking-wide">Chatlet</h1>
        <button
          onClick={() => setDark(d => !d)}
          className={`text-xs px-2 py-1 rounded ${inputBg} ${textMuted} hover:opacity-80`}
        >
          {dark ? "☀️" : "🌙"}
        </button>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className={`flex flex-col items-center justify-center h-full ${textMuted} text-sm`}>
            <p>No messages yet</p>
            <p className="text-xs mt-1">Send a message to start a chat</p>
          </div>
        )}
        <div className="space-y-4 max-w-2xl mx-auto">
          {messages.map((msg, i) => (
            <div key={i} className={`${msg.role === "user" ? "text-right" : "text-left"}`}>
              <div
                className={`inline-block max-w-[85%] px-3 py-2 rounded-xl text-sm ${
                  msg.role === "user"
                    ? dark ? "bg-blue-600 text-white" : "bg-blue-500 text-white"
                    : dark ? "bg-zinc-800 text-zinc-100" : "bg-zinc-100 text-zinc-900"
                }`}
              >
                {msg.content}
              </div>
              {msg.toolOutputs && msg.toolOutputs.length > 0 && (
                <div className={`mt-2 space-y-2 ${msg.role === "user" ? "max-w-[85%] ml-auto" : ""}`}>
                  {msg.toolOutputs.map((output, j) => (
                    <ToolCard key={j} output={output} dark={dark} />
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
      </main>

      {/* Input */}
      <footer className={`border-t ${borderSubtle} p-3`}>
        <div className="flex gap-2 max-w-2xl mx-auto">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && send()}
            placeholder="Type a message..."
            className={`flex-1 px-3 py-2 rounded-lg text-sm ${inputBg} ${textPrimary} placeholder:${textMuted} outline-none border ${borderSubtle} focus:ring-1 focus:ring-blue-500`}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-40 hover:opacity-90"
          >
            Send
          </button>
        </div>
        <p className={`text-center text-xs mt-2 ${textMuted}`}>
          Chatlet powered by {frameworkName}
        </p>
      </footer>
    </div>
  );
}

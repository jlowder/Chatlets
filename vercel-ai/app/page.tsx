'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';

interface ToolOutput {
  stdout?: string;
  stderr?: string;
  error?: string;
}

export default function ChatPage() {
  const [dark, setDark] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; text: string; toolOutputs: ToolOutput[] }[]>([]);
  const [loading, setLoading] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const bg = dark ? 'bg-zinc-950 text-zinc-50' : 'bg-zinc-50 text-zinc-900';
  const border = dark ? 'border-zinc-800' : 'border-zinc-200';
  const borderSubtle = dark ? 'border-zinc-700' : 'border-zinc-300';
  const cardBg = dark ? 'bg-zinc-900' : 'bg-white';
  const cardBorder = dark ? 'border-zinc-800' : 'border-zinc-200';
  const mutedText = dark ? 'text-zinc-600' : 'text-zinc-400';
  const mutedTextHover = dark ? 'text-zinc-400' : 'text-zinc-500';
  const toolCardBg = dark ? 'bg-zinc-800' : 'bg-zinc-100';
  const inputBg = dark ? 'bg-zinc-900 border-zinc-700' : 'bg-white border-zinc-300';

  useLayoutEffect(() => {
    setTimeout(() => {
      const container = chatRef.current;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }, 0);
  }, [messages, loading]);

  useEffect(() => {
    const timer = setTimeout(() => {
      promptRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, [messages]);

  const handleSend = async () => {
    const trimmed = prompt.trim();
    if (!trimmed || loading) return;

    setMessages(prev => [...prev, { role: 'user', text: trimmed, toolOutputs: [] }]);
    setPrompt('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: trimmed }),
      });
      const data = await res.json();
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: data.text ?? '',
          toolOutputs: data.toolOutputs ?? [],
        },
      ]);
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: 'Something went wrong. Please try again.', toolOutputs: [] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`min-h-screen flex flex-col ${dark ? 'bg-zinc-900' : 'bg-zinc-200'} items-center pt-8 pb-8`}>
      <button
        type="button"
        onClick={() => setDark(d => !d)}
        className={`fixed top-4 right-4 z-50 text-xs px-3 py-1.5 rounded-full border transition-colors ${
          dark
            ? 'bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700'
            : 'bg-white border-zinc-300 text-zinc-600 hover:bg-zinc-100'
        }`}
      >
        {dark ? 'Light mode' : 'Dark mode'}
      </button>
      <div className={`w-full max-w-3xl flex flex-col ${bg} rounded-2xl shadow-2xl overflow-hidden border ${border}`}>
      {/* Header */}
      <header className={`flex items-center justify-between px-6 py-4 border-b ${border}`}>
        <h1 className="text-lg font-semibold tracking-tight">Chat</h1>
      </header>

      {/* Chat area */}
      <div
        ref={chatRef}
        className="flex-1 min-h-0 overflow-y-auto px-8 py-6 pb-20 space-y-6"
      >
        {messages.length === 0 && !loading && (
          <div className={`text-center ${mutedText} text-sm mt-20`}>
            Send a message to get started.
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            data-scroll-target
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : `${cardBg} border ${cardBorder}`
              }`}
            >
              {msg.text && <p>{msg.text}</p>}

              {/* Inline tool output cards */}
              {msg.toolOutputs.length > 0 && (
                <div className="mt-3 space-y-2">
                  {msg.toolOutputs.map((out, i) => (
                    <ToolCard key={i} output={out} dark={dark} />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className={`rounded-2xl ${cardBg} border ${cardBorder} px-4 py-3 shadow-sm`}>
              <TypingIndicator dark={dark} />
            </div>
          </div>
        )}
      </div>

      {/* Bottom input bar */}
      <div className={`sticky bottom-0 border-t ${border} ${cardBg} px-6 py-4`} data-input-bar>
        <div className="flex items-end gap-3">
          <textarea
            ref={promptRef}
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Type a message..."
            rows={1}
            className={`flex-1 resize-none rounded-xl border ${inputBg} px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent transition-shadow`}
            disabled={loading}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={loading || !prompt.trim()}
            className="flex-shrink-0 h-11 px-5 rounded-full bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            Send
          </button>
        </div>
      </div>

      {/* Footer */}
      <footer className={`px-6 py-3 text-center text-xs ${mutedText} border-t ${border}`}>
        Chatlet powered by Vercel AI SDK
      </footer>
      </div>
    </div>
  );
}

function ToolCard({ output, dark }: { output: ToolOutput; dark: boolean }) {
  const toolCardBg = dark ? 'bg-zinc-800' : 'bg-zinc-100';
  const borderSubtle = dark ? 'border-zinc-700' : 'border-zinc-300';
  return (
    <div className={`rounded-xl ${toolCardBg} border ${borderSubtle} overflow-hidden text-xs`}>
      {output.error && (
        <div className="px-3 py-2 text-red-600 font-medium">
          {output.error}
        </div>
      )}
      {output.stdout && (
        <div className="px-3 py-2">
          <div className="text-green-700 font-medium mb-1">stdout</div>
          <pre className="text-green-800 whitespace-pre-wrap font-mono text-xs leading-relaxed">
            {output.stdout}
          </pre>
        </div>
      )}
      {output.stderr && (
        <div className={`px-3 py-2 border-t ${borderSubtle}`}>
          <div className="text-red-700 font-medium mb-1">stderr</div>
          <pre className="text-red-800 whitespace-pre-wrap font-mono text-xs leading-relaxed">
            {output.stderr}
          </pre>
        </div>
      )}
    </div>
  );
}

function TypingIndicator({ dark }: { dark: boolean }) {
  const dotColor = dark ? 'bg-zinc-500' : 'bg-zinc-400';
  return (
    <div className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-bounce`} style={{ animationDelay: '0ms' }} />
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-bounce`} style={{ animationDelay: '150ms' }} />
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-bounce`} style={{ animationDelay: '300ms' }} />
    </div>
  );
}

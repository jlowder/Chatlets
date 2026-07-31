export default function TypingIndicator({ dark }: { dark: boolean }) {
  const dotColor = dark ? 'bg-zinc-500' : 'bg-zinc-400';
  return (
    <div className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-bounce`} style={{ animationDelay: '0ms' }} />
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-bounce`} style={{ animationDelay: '150ms' }} />
      <span className={`w-2 h-2 rounded-full ${dotColor} animate-bounce`} style={{ animationDelay: '300ms' }} />
    </div>
  );
}

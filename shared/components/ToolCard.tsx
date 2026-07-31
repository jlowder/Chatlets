interface ToolOutput {
  stdout?: string;
  stderr?: string;
  error?: string;
}

export default function ToolCard({ output, dark }: { output: ToolOutput; dark: boolean }) {
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

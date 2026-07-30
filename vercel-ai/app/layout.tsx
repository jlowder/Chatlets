import './globals.css';

export const metadata = {
  title: 'Chat with LLM',
  description: 'A simple LLM chat interface',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        {children}
      </body>
    </html>
  );
}

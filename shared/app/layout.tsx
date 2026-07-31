import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chatlet",
  description: "AI chat interface - reusable across frameworks",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

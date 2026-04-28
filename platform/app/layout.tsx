import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ella-chat-publish admin",
  description: "Local admin console for ella-chat-publish (SFW Telegram bot)",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}

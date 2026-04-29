import type { Metadata } from "next";
import "./globals.css";

import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { Toaster } from "@/components/ui/sonner";

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
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <Header />
            <main className="flex-1 overflow-auto">{children}</main>
          </div>
        </div>
        <Toaster />
      </body>
    </html>
  );
}

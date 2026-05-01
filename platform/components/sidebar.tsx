"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Network,
  Settings2,
  FileText,
  Users,
  BookOpen,
  Image as ImageIcon,
  Workflow,
  ScrollText,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  enabled: boolean;
};

const items: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, enabled: true },
  { href: "/connections", label: "Connections", icon: Network, enabled: true },
  { href: "/env", label: "Env", icon: Settings2, enabled: true },
  { href: "/prompts", label: "Prompts", icon: FileText, enabled: true },
  { href: "/characters", label: "Characters", icon: Users, enabled: true },
  { href: "/lorebook", label: "Lorebook", icon: BookOpen, enabled: true },
  { href: "/config", label: "Image Config", icon: ImageIcon, enabled: true },
  { href: "/workflows", label: "Workflows", icon: Workflow, enabled: true },
  { href: "/logs", label: "Logs", icon: ScrollText, enabled: true },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 border-r bg-muted/30 md:block">
      <div className="flex h-14 items-center border-b px-4">
        <span className="text-sm font-semibold tracking-tight">
          Chatbot Manager
        </span>
      </div>
      <nav className="flex flex-col gap-1 p-3">
        {items.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          const base = "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors";
          if (!item.enabled) {
            return (
              <span
                key={item.href}
                className={cn(
                  base,
                  "cursor-not-allowed text-muted-foreground/60",
                )}
                title="Activates in a later milestone"
              >
                <Icon className="h-4 w-4" />
                {item.label}
                <span className="ml-auto text-[10px] uppercase tracking-wider opacity-60">
                  soon
                </span>
              </span>
            );
          }
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                base,
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

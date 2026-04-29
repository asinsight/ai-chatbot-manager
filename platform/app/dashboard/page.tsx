import { BotStatusCard } from "@/components/bot-status-card";
import { ConnectionsHealthCard } from "@/components/connections-health-card";
import { LogTail } from "@/components/log-tail";

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          봇 상태와 최근 로그.
        </p>
      </div>
      <BotStatusCard />
      <ConnectionsHealthCard />
      <LogTail />
    </div>
  );
}

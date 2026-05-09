"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { propertiesApi } from "@/lib/api-client";

interface HeaderProps {
  title: string;
  propertyId: number;
  lastSynced: string | null;
}

export function Header({ title, propertyId, lastSynced }: HeaderProps) {
  const [syncing, setSyncing] = useState(false);

  async function handleSync() {
    setSyncing(true);
    try {
      await propertiesApi.triggerSync(propertyId, "ga4");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
      <h1 className="text-lg font-semibold text-white">{title}</h1>
      <div className="flex items-center gap-4">
        {lastSynced && (
          <span className="text-xs text-slate-500">
            Last synced {new Date(lastSynced).toLocaleString()}
          </span>
        )}
        <button
          onClick={handleSync}
          disabled={syncing}
          title="Trigger manual sync"
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-400 hover:border-slate-600 hover:text-white transition disabled:opacity-50"
        >
          <RefreshCw size={12} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Syncing…" : "Sync now"}
        </button>
      </div>
    </header>
  );
}

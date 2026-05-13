"use client";

import { useSearchParams } from "next/navigation";
import { Construction } from "lucide-react";
import { Sidebar } from "@/components/layout/sidebar";

export default function ExplorePage() {
  const params = useSearchParams();
  const propertyId = Number(params.get("property_id") ?? 0);

  return (
    <div className="flex h-screen bg-slate-950">
      <Sidebar propertyId={propertyId} />
      <main className="flex flex-1 flex-col items-center justify-center gap-4">
        <Construction size={40} className="text-slate-600" />
        <h1 className="text-xl font-semibold text-white">Explore</h1>
        <p className="text-sm text-slate-500">
          The data explorer is coming in Phase 2H. For now, use the Chat to explore your data.
        </p>
      </main>
    </div>
  );
}

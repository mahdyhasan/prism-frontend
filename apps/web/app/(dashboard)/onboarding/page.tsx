"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { propertiesApi } from "@/lib/api-client";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<"name" | "ga4" | "done">("name");
  const [propertyId, setPropertyId] = useState<number | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [ga4Id, setGa4Id] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreateProperty() {
    if (!displayName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const prop = await propertiesApi.create({ display_name: displayName.trim(), timezone });
      setPropertyId(prop.id);
      setStep("ga4");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLinkGA4() {
    if (!propertyId || !ga4Id.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await propertiesApi.linkGA4(propertyId, ga4Id.trim());
      // Kick off initial backfill
      await propertiesApi.triggerSync(propertyId, "ga4");
      setStep("done");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (step === "done") {
    return (
      <OnboardingShell step={3}>
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-900 text-3xl">
            ✓
          </div>
          <h2 className="mb-2 text-xl font-bold text-white">All set.</h2>
          <p className="mb-6 text-slate-400">
            GA4 linked. Your first data pull is running in the background — it typically takes a few
            minutes for 14 months of history.
          </p>
          <button
            onClick={() => router.push(`/properties/${propertyId}/overview`)}
            className="rounded-xl bg-brand-600 px-6 py-3 text-sm font-semibold text-white hover:bg-brand-700 transition"
          >
            Go to dashboard
          </button>
        </div>
      </OnboardingShell>
    );
  }

  return (
    <OnboardingShell step={step === "name" ? 1 : 2}>
      {step === "name" && (
        <div>
          <h2 className="mb-1 text-xl font-bold text-white">Name your property</h2>
          <p className="mb-6 text-sm text-slate-400">
            A property is one website or app you want to track. You can add more later.
          </p>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">
                Property name
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="augmex.io"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">
                Timezone
              </label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white focus:border-brand-500 focus:outline-none"
              >
                <option value="UTC">UTC</option>
                <option value="Asia/Dhaka">Asia/Dhaka (GMT+6)</option>
                <option value="America/New_York">America/New_York (EST)</option>
                <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
                <option value="Europe/London">Europe/London (GMT)</option>
              </select>
            </div>
            {error && <ErrorBanner message={error} />}
            <button
              onClick={handleCreateProperty}
              disabled={loading || !displayName.trim()}
              className="w-full rounded-xl bg-brand-600 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {loading ? "Creating…" : "Continue"}
            </button>
          </div>
        </div>
      )}

      {step === "ga4" && (
        <div>
          <h2 className="mb-1 text-xl font-bold text-white">Connect Google Analytics 4</h2>
          <p className="mb-6 text-sm text-slate-400">
            Enter your GA4 property ID. Find it in GA4 under Admin → Property → Property details.
          </p>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">
                GA4 Property ID
              </label>
              <input
                type="text"
                value={ga4Id}
                onChange={(e) => setGa4Id(e.target.value)}
                placeholder="properties/123456789"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
              />
              <p className="mt-1.5 text-xs text-slate-500">
                Format: <code className="text-slate-400">properties/XXXXXXXXX</code>
              </p>
            </div>
            {error && <ErrorBanner message={error} />}
            <button
              onClick={handleLinkGA4}
              disabled={loading || !ga4Id.trim()}
              className="w-full rounded-xl bg-brand-600 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {loading ? "Verifying access…" : "Link GA4 property"}
            </button>
            <button
              onClick={() => router.push(`/properties/${propertyId}/overview`)}
              className="w-full rounded-xl border border-slate-700 py-3 text-sm font-medium text-slate-400 hover:text-white transition"
            >
              Skip for now
            </button>
          </div>
        </div>
      )}
    </OnboardingShell>
  );
}

function OnboardingShell({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-xl font-black text-white">
            P
          </div>
          <div className="flex items-center justify-center gap-2">
            {[1, 2, 3].map((s) => (
              <div
                key={s}
                className={`h-1.5 w-8 rounded-full transition-all ${
                  s <= step ? "bg-brand-500" : "bg-slate-800"
                }`}
              />
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8">{children}</div>
      </div>
    </main>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
      {message}
    </div>
  );
}

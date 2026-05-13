"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { propertiesApi, propertiesApiExt } from "@/lib/api-client";

type Step = "name" | "ga4" | "gsc";

interface NewPropertyModalProps {
  open: boolean;
  onClose: () => void;
}

const TIMEZONES: { value: string; label: string }[] = [
  { value: "UTC", label: "UTC" },
  { value: "Asia/Dhaka", label: "Asia/Dhaka (GMT+6)" },
  { value: "America/New_York", label: "America/New_York (EST)" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles (PST)" },
  { value: "Europe/London", label: "Europe/London (GMT)" },
];

export function NewPropertyModal({ open, onClose }: NewPropertyModalProps) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<Step>("name");
  const [propertyId, setPropertyId] = useState<number | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [ga4Id, setGa4Id] = useState("");
  const [gscUrl, setGscUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state every time the modal opens.
  useEffect(() => {
    if (open) {
      setStep("name");
      setPropertyId(null);
      setDisplayName("");
      setTimezone("UTC");
      setGa4Id("");
      setGscUrl("");
      setLoading(false);
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  function close() {
    setError(null);
    onClose();
  }

  async function handleCreate() {
    if (!displayName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const prop = await propertiesApi.create({
        display_name: displayName.trim(),
        timezone,
      });
      setPropertyId(prop.id);
      // Refresh property list cache so the sidebar switcher sees the new entry.
      await queryClient.invalidateQueries({ queryKey: ["properties"] });
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
      // Trigger background backfill silently — failures here shouldn't block UX.
      void propertiesApi.triggerSync(propertyId, "ga4").catch(() => {});
      await queryClient.invalidateQueries({ queryKey: ["properties"] });
      await queryClient.invalidateQueries({ queryKey: ["property", propertyId] });
      setStep("gsc");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleLinkGSC() {
    if (!propertyId || !gscUrl.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await propertiesApiExt.linkGSC(propertyId, gscUrl.trim());
      await queryClient.invalidateQueries({ queryKey: ["properties"] });
      await queryClient.invalidateQueries({ queryKey: ["property", propertyId] });
      finishAndNavigate();
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
  }

  function finishAndNavigate() {
    if (!propertyId) {
      close();
      return;
    }
    close();
    router.push(`/properties/${propertyId}/overview`);
  }

  function skipGA4() {
    setError(null);
    setStep("gsc");
  }

  function skipGSC() {
    finishAndNavigate();
  }

  const stepIndex = step === "name" ? 1 : step === "ga4" ? 2 : 3;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={close}
    >
      <div
        className="relative w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={close}
          aria-label="Close"
          className="absolute right-4 top-4 text-slate-500 hover:text-white transition"
        >
          <X size={18} />
        </button>

        <div className="mb-6 flex items-center justify-center gap-2">
          {[1, 2, 3].map((s) => (
            <div
              key={s}
              className={`h-1.5 w-8 rounded-full transition-all ${
                s <= stepIndex ? "bg-brand-500" : "bg-slate-800"
              }`}
            />
          ))}
        </div>

        {step === "name" && (
          <div>
            <h2 className="mb-1 text-xl font-bold text-white">Add a new property</h2>
            <p className="mb-6 text-sm text-slate-400">
              A property is one website or app you want to track.
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
                  {TIMEZONES.map((tz) => (
                    <option key={tz.value} value={tz.value}>
                      {tz.label}
                    </option>
                  ))}
                </select>
              </div>
              {error && <ErrorBanner message={error} />}
              <button
                onClick={handleCreate}
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
              Optional. You can link GA4 later from this property's settings.
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
                  Format: <code className="text-slate-400">properties/509732559</code>
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
                onClick={skipGA4}
                disabled={loading}
                className="w-full rounded-xl border border-slate-700 py-3 text-sm font-medium text-slate-400 hover:text-white transition disabled:opacity-50"
              >
                Skip for now
              </button>
            </div>
          </div>
        )}

        {step === "gsc" && (
          <div>
            <h2 className="mb-1 text-xl font-bold text-white">Connect Search Console</h2>
            <p className="mb-6 text-sm text-slate-400">
              Optional. You can link GSC later from this property's settings.
            </p>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  GSC site URL
                </label>
                <input
                  type="text"
                  value={gscUrl}
                  onChange={(e) => setGscUrl(e.target.value)}
                  placeholder="sc-domain:augmex.io"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
                />
                <p className="mt-1.5 text-xs text-slate-500">
                  Use <code className="text-slate-400">sc-domain:example.com</code> or{" "}
                  <code className="text-slate-400">https://example.com/</code>
                </p>
              </div>
              {error && <ErrorBanner message={error} />}
              <button
                onClick={handleLinkGSC}
                disabled={loading || !gscUrl.trim()}
                className="w-full rounded-xl bg-brand-600 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                {loading ? "Linking…" : "Link Search Console"}
              </button>
              <button
                onClick={skipGSC}
                disabled={loading}
                className="w-full rounded-xl border border-slate-700 py-3 text-sm font-medium text-slate-400 hover:text-white transition disabled:opacity-50"
              >
                Skip and finish
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
      {message}
    </div>
  );
}

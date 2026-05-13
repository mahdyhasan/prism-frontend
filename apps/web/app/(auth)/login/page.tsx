"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import {
  APIError,
  authApi,
  setStoredToken,
  type GoogleDiscoverResponse,
} from "@/lib/api-client";

type Phase =
  | "idle"               // no Google session yet
  | "google_signing_in"  // Google session active, calling /auth/sync
  | "discovering"        // /auth/sync 404 → fetching the user's GA4/GSC lists
  | "needs_registration" // dropdowns ready, awaiting user picks
  | "registering"        // submitting the registration
  | "linking_google";    // legacy: email/password user linking Google in settings

export default function LoginPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("idle");
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [discovery, setDiscovery] = useState<GoogleDiscoverResponse | null>(null);
  const signInAttempted = useRef(false);

  // ── Google sign-in / discover / registration ─────────────────────────────
  useEffect(() => {
    if (status !== "authenticated" || !session?.googleIdToken) return;
    if (signInAttempted.current) return;
    signInAttempted.current = true;

    // Legacy link-google flow (admin connecting Google from Settings)
    const isLinkAttempt =
      typeof window !== "undefined" &&
      sessionStorage.getItem("prism_link_google") === "true";

    if (isLinkAttempt) {
      sessionStorage.removeItem("prism_link_google");
      setPhase("linking_google");
      authApi
        .linkGoogle(session.googleIdToken!, session.googleRefreshToken ?? "")
        .then((res) => {
          setStoredToken(res.access_token);
          router.replace(
            res.property_id ? `/properties/${res.property_id}/settings` : "/properties",
          );
        })
        .catch((err: Error) => {
          setGoogleError(err.message);
          setPhase("idle");
        });
      return;
    }

    // Normal flow: try /auth/sync, on 404 fetch discovery, then show form
    setPhase("google_signing_in");
    (async () => {
      try {
        const res = await authApi.sync({
          google_id_token: session.googleIdToken!,
          google_refresh_token: session.googleRefreshToken ?? "",
          name: session.user?.name ?? "",
          email: session.user?.email ?? "",
          google_sub: session.googleSub ?? "",
        });
        setStoredToken(res.access_token);
        router.replace(
          res.property_id ? `/properties/${res.property_id}/overview` : "/properties",
        );
      } catch (err: unknown) {
        if (!(err instanceof APIError) || err.status !== 404) {
          setGoogleError(err instanceof Error ? err.message : "Sign in failed.");
          setPhase("idle");
          return;
        }

        // New user — fetch their accessible GA4 properties + GSC sites
        setPhase("discovering");
        try {
          const disc = await authApi.discover({
            google_id_token: session.googleIdToken!,
            google_access_token: session.googleAccessToken,
            google_refresh_token: session.googleRefreshToken,
          });
          setDiscovery(disc);
          setPhase("needs_registration");
        } catch (dErr: unknown) {
          setGoogleError(
            dErr instanceof Error
              ? `Couldn't list your Google properties: ${dErr.message}`
              : "Discovery failed.",
          );
          setPhase("idle");
        }
      }
    })();
  }, [session, status, router]);

  // ── Render ───────────────────────────────────────────────────────────────
  if (
    status === "loading" ||
    phase === "google_signing_in" ||
    phase === "linking_google" ||
    phase === "discovering"
  ) {
    const label =
      phase === "linking_google"
        ? "Linking your Google account…"
        : phase === "discovering"
          ? "Finding your GA4 properties…"
          : "Signing you in…";
    return <LoadingScreen label={label} />;
  }

  if (phase === "registering") {
    return <LoadingScreen label="Setting up your dashboard…" />;
  }

  if (phase === "needs_registration" && discovery) {
    return (
      <RegistrationForm
        userName={session?.user?.name ?? ""}
        userEmail={session?.user?.email ?? ""}
        discovery={discovery}
        onSubmit={async (form) => {
          if (!session?.googleIdToken || !session?.googleSub) {
            setGoogleError("Google session expired. Please sign in again.");
            return;
          }
          setPhase("registering");
          setGoogleError(null);
          try {
            const res = await authApi.registerGoogle({
              google_id_token: session.googleIdToken,
              google_refresh_token: session.googleRefreshToken ?? "",
              google_sub: session.googleSub,
              email: session.user?.email ?? "",
              name: session.user?.name ?? "",
              ga4_property_id: form.ga4PropertyId,
              gsc_site_url: form.gscSiteUrl || undefined,
              display_name: form.displayName || undefined,
              timezone: form.timezone,
            });
            setStoredToken(res.access_token);
            router.replace(
              res.property_id ? `/properties/${res.property_id}/overview` : "/properties",
            );
          } catch (err: unknown) {
            setGoogleError(err instanceof Error ? err.message : "Registration failed.");
            setPhase("needs_registration");
          }
        }}
        onCancel={() => {
          signOut({ redirect: false });
          signInAttempted.current = false;
          setDiscovery(null);
          setPhase("idle");
          setGoogleError(null);
        }}
        error={googleError}
      />
    );
  }

  return <SignInScreen googleError={googleError} onGoogle={() => signIn("google")} />;
}

// ── Sign-in screen ─────────────────────────────────────────────────────────

function SignInScreen({
  googleError,
  onGoogle,
}: {
  googleError: string | null;
  onGoogle: () => void;
}) {
  const [showAdmin, setShowAdmin] = useState(false);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-600 text-3xl font-black text-white shadow-lg">
            P
          </div>
          <h1 className="text-2xl font-bold text-white">PRISM</h1>
          <p className="mt-1 text-sm text-slate-500">Analytics Platform</p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8">
          <h2 className="mb-1 text-lg font-bold text-white">Welcome</h2>
          <p className="mb-6 text-sm text-slate-400">
            Sign in with Google. New users will register a property in the next step.
          </p>

          {googleError && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
              <span>{googleError}</span>
            </div>
          )}

          <button
            onClick={onGoogle}
            className="flex w-full items-center justify-center gap-3 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100 active:scale-[0.98]"
          >
            <GoogleIcon />
            Continue with Google
          </button>

          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-slate-800" />
            <span className="text-xs uppercase tracking-wider text-slate-600">or</span>
            <div className="h-px flex-1 bg-slate-800" />
          </div>

          <button
            onClick={() => setShowAdmin(!showAdmin)}
            className="w-full text-center text-xs font-semibold text-slate-500 hover:text-slate-300 transition"
          >
            {showAdmin ? "Hide admin login" : "Admin login (email + password)"}
          </button>

          {showAdmin && <AdminLogin />}
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">
          By signing in you agree to our terms of service.
        </p>
      </div>
    </main>
  );
}

// ── Admin email/password login ─────────────────────────────────────────────

function AdminLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await authApi.login(email, password);
      setStoredToken(res.access_token);
      router.replace(
        res.property_id ? `/properties/${res.property_id}/overview` : "/onboarding",
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-3">
      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950 p-2.5 text-xs text-red-400">
          {error}
        </div>
      )}

      <button
        type="button"
        onClick={() => {
          setEmail("mahdyhasan@gmail.com");
          setPassword("Prism@2026!");
        }}
        className="w-full rounded-lg border border-dashed border-slate-700 py-1.5 text-xs text-slate-600 transition hover:border-slate-500 hover:text-slate-400"
      >
        ⚡ Dev autofill
      </button>

      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="admin@example.com"
        className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
      />

      <div className="relative">
        <input
          type={showPw ? "text" : "password"}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 pr-10 text-sm text-white placeholder-slate-500 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
        />
        <button
          type="button"
          onClick={() => setShowPw(!showPw)}
          className="absolute inset-y-0 right-3 flex items-center text-slate-500 hover:text-slate-300"
        >
          {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-800 border border-slate-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading && <Loader2 size={15} className="animate-spin" />}
        Sign in as admin
      </button>
    </form>
  );
}

// ── Registration form (new Google user) ────────────────────────────────────

function RegistrationForm({
  userName,
  userEmail,
  discovery,
  onSubmit,
  onCancel,
  error,
}: {
  userName: string;
  userEmail: string;
  discovery: GoogleDiscoverResponse;
  onSubmit: (form: {
    ga4PropertyId: string;
    gscSiteUrl: string;
    displayName: string;
    timezone: string;
  }) => void;
  onCancel: () => void;
  error: string | null;
}) {
  const ga4List = discovery.ga4_properties;
  const gscList = discovery.gsc_sites;

  const [ga4PropertyId, setGa4PropertyId] = useState(
    ga4List[0]?.property_id ?? "",
  );
  const [gscSiteUrl, setGscSiteUrl] = useState(""); // start empty — user opts in
  const [displayName, setDisplayName] = useState(() => {
    // Default to first GA4 property's display name; fallback to email domain
    if (ga4List[0]) return ga4List[0].display_name;
    return userEmail.includes("@") ? userEmail.split("@")[1] : "";
  });
  const [timezone, setTimezone] = useState(
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
      : "UTC",
  );

  // Keep the displayName in sync with the selected GA4 property until the user
  // edits it manually
  const userEditedName = useRef(false);
  const handleGa4Change = (v: string) => {
    setGa4PropertyId(v);
    if (!userEditedName.current) {
      const match = ga4List.find((p) => p.property_id === v);
      if (match) setDisplayName(match.display_name);
    }
  };

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ga4PropertyId.trim()) return;
    onSubmit({
      ga4PropertyId: ga4PropertyId.trim(),
      gscSiteUrl: gscSiteUrl.trim(),
      displayName: displayName.trim(),
      timezone,
    });
  }

  // ── Empty GA4 list: blocking error ────────────────────────────────────
  if (ga4List.length === 0) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4">
        <div className="w-full max-w-md">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/15">
              <AlertCircle size={26} className="text-amber-400" />
            </div>
            <h1 className="text-xl font-bold text-white">No GA4 properties found</h1>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              We couldn't find any Google Analytics 4 properties for{" "}
              <span className="font-medium text-slate-200">{userEmail}</span>.
            </p>
            <p className="mt-3 text-sm text-slate-400">
              Make sure you have at least <span className="font-semibold text-white">Viewer</span>{" "}
              access in <span className="font-mono text-slate-300">GA4 → Admin → Account access</span>,
              then sign in again.
            </p>
            <button
              onClick={onCancel}
              className="mt-5 w-full rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Back to sign in
            </button>
          </div>

          <p className="mt-6 text-center text-xs text-slate-600">
            Signed in as {userEmail}
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4 py-8">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-600 text-3xl font-black text-white shadow-lg">
            P
          </div>
          <h1 className="text-2xl font-bold text-white">
            Welcome{userName ? `, ${userName.split(" ")[0]}` : ""}
          </h1>
          <p className="mt-1 text-sm text-slate-500">Choose what to track.</p>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8">
          {error && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field
              label="GA4 Property"
              hint={`${ga4List.length} ${ga4List.length === 1 ? "property" : "properties"} available`}
            >
              <select
                value={ga4PropertyId}
                onChange={(e) => handleGa4Change(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              >
                {ga4List.map((p) => (
                  <option key={p.property_id} value={p.property_id}>
                    {p.account_name} → {p.display_name} ({p.property_id})
                  </option>
                ))}
              </select>
            </Field>

            <Field
              label={
                <>
                  Search Console site{" "}
                  <span className="font-normal text-slate-600">(optional)</span>
                </>
              }
              hint={
                gscList.length === 0
                  ? "No verified Search Console sites found for this Google account — you can add one later from Settings."
                  : "Optional. Adds search rankings + click data on top of GA4."
              }
            >
              <select
                value={gscSiteUrl}
                onChange={(e) => setGscSiteUrl(e.target.value)}
                disabled={gscList.length === 0}
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">
                  {gscList.length === 0 ? "(none available)" : "— Skip for now —"}
                </option>
                {gscList.map((s) => (
                  <option key={s.site_url} value={s.site_url}>
                    {s.site_url}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Display name" hint="A friendly label for this dashboard">
              <input
                type="text"
                required
                value={displayName}
                onChange={(e) => {
                  userEditedName.current = true;
                  setDisplayName(e.target.value);
                }}
                placeholder="My website"
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white placeholder-slate-600 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              />
            </Field>

            <Field label="Timezone">
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2.5 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              >
                <option value="UTC">UTC</option>
                <option value="Asia/Dhaka">Asia/Dhaka (GMT+6)</option>
                <option value="America/New_York">America/New_York (EST)</option>
                <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
                <option value="Europe/London">Europe/London (GMT)</option>
                {/* Fallback for browsers / users with other zones */}
                {!["UTC","Asia/Dhaka","America/New_York","America/Los_Angeles","Europe/London"].includes(timezone) && (
                  <option value={timezone}>{timezone}</option>
                )}
              </select>
            </Field>

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={onCancel}
                className="rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-400 transition hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!ga4PropertyId}
                className="flex-1 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Create my dashboard
              </button>
            </div>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">
          Signed in as {userEmail}
        </p>
      </div>
    </main>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold text-slate-400">{label}</label>
      {children}
      {hint && <p className="mt-1.5 text-xs text-slate-600">{hint}</p>}
    </div>
  );
}

// ── Shared ─────────────────────────────────────────────────────────────────

function LoadingScreen({ label }: { label: string }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950">
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        <p className="text-sm text-slate-400">{label}</p>
      </div>
    </main>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48">
      <path fill="#FFC107" d="M43.6 20.2H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34 6.6 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.7-.4-3.8z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 15.8 19 13 24 13c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34 6.6 29.3 4 24 4c-7.6 0-14.2 4.3-17.7 10.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.5 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8H6.3C9.7 39.5 16.4 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.2H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.3 5.6l6.2 5.2C37 37.6 44 32 44 24c0-1.3-.1-2.7-.4-3.8z" />
    </svg>
  );
}

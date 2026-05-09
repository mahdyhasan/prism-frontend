"use client";

import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { authApi, setStoredToken } from "@/lib/api-client";

export default function LoginPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // After NextAuth completes, exchange tokens with the PRISM backend
  useEffect(() => {
    if (status !== "authenticated" || !session?.googleIdToken) return;
    if (syncing) return;

    setSyncing(true);
    authApi
      .sync({
        google_id_token: session.googleIdToken!,
        google_refresh_token: session.googleRefreshToken ?? "",
        name: session.user?.name ?? "",
        email: session.user?.email ?? "",
        google_sub: session.googleSub ?? "",
      })
      .then((res) => {
        setStoredToken(res.access_token);
        router.replace("/onboarding");
      })
      .catch((err: Error) => {
        setError(err.message);
        setSyncing(false);
      });
  }, [session, status, syncing, router]);

  if (status === "loading" || syncing) {
    return <LoadingScreen label={syncing ? "Signing you in…" : "Loading…"} />;
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-600 text-3xl font-black text-white shadow-lg">
            P
          </div>
          <h1 className="text-2xl font-bold text-white">PRISM</h1>
          <p className="mt-1 text-sm text-slate-500">Augmex Analytics Platform</p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8">
          <h2 className="mb-2 text-lg font-semibold text-white">Sign in</h2>
          <p className="mb-6 text-sm text-slate-400">
            Connect with Google to access your analytics.
          </p>

          {error && (
            <div className="mb-4 rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <button
            onClick={() => signIn("google")}
            className="flex w-full items-center justify-center gap-3 rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-700 active:scale-95"
          >
            <GoogleIcon />
            Continue with Google
          </button>

          <p className="mt-6 text-center text-xs text-slate-600">
            Access restricted to authorised Augmex team members.
          </p>
        </div>
      </div>
    </main>
  );
}

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
      <path
        fill="#FFC107"
        d="M43.6 20.2H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34 6.6 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.7-.4-3.8z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.6 15.8 19 13 24 13c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34 6.6 29.3 4 24 4c-7.6 0-14.2 4.3-17.7 10.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.5 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8H6.3C9.7 39.5 16.4 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.2H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.3 5.6l6.2 5.2C37 37.6 44 32 44 24c0-1.3-.1-2.7-.4-3.8z"
      />
    </svg>
  );
}

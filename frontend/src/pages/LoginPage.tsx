import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { useAuth } from "../auth/context";
import { config, isFirebaseConfigured } from "../config/env";

export default function LoginPage() {
  const { signInWithGoogle, signInDev } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const onGoogle = async () => {
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch (error) {
      const code = (error as { code?: string }).code;
      if (code !== "auth/popup-closed-by-user" && code !== "auth/cancelled-popup-request") {
        toast.error("Google sign-in failed", { description: (error as Error).message });
      }
    } finally {
      setBusy(false);
    }
  };

  const onDev = (event: FormEvent) => {
    event.preventDefault();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      toast.error("Enter a valid email");
      return;
    }
    signInDev(email);
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="card w-full max-w-sm p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-semibold">NIFTY 50 Alerts</h1>
            <p className="text-sm text-muted">Live Indian market prices with price alerts</p>
          </div>
        </div>

        {isFirebaseConfigured && (
          <button
            type="button"
            onClick={onGoogle}
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 py-2.5 font-medium hover:bg-surface-2 disabled:opacity-60"
          >
            <svg viewBox="0 0 48 48" className="h-5 w-5" aria-hidden="true">
              <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
              <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
              <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
              <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
            </svg>
            Continue with Google
          </button>
        )}

        {config.authDevMode && (
          <form onSubmit={onDev} className={isFirebaseConfigured ? "mt-6 border-t border-line pt-6" : ""}>
            <label htmlFor="dev-email" className="mb-1 block text-sm font-medium">
              Dev login (local testing only)
            </label>
            <input
              id="dev-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-lg border border-line bg-surface-2 px-3 py-2 outline-none focus:border-accent"
            />
            <button
              type="submit"
              className="mt-3 w-full rounded-lg bg-accent px-4 py-2.5 font-medium text-accent-fg hover:opacity-90"
            >
              Continue
            </button>
            <p className="mt-2 text-xs text-muted">
              Turn this off (AUTH_DEV_MODE=false) once Google login is set up.
            </p>
          </form>
        )}

        {!isFirebaseConfigured && !config.authDevMode && (
          <p className="text-sm text-muted">
            Login isn't configured yet. Add your Firebase web config (VITE_FIREBASE_*) to the .env
            file and restart the app.
          </p>
        )}
      </div>
    </main>
  );
}

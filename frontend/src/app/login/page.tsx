"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseClient } from "@/lib/supabase";


type Mode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const checkSession = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data } = await supabase.auth.getSession();
        if (data.session) {
          router.push("/");
        }
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Missing Supabase configuration");
      }
    };
    checkSession();
  }, [router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);

    try {
      const supabase = getSupabaseClient();
      if (mode === "signin") {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.push("/");
        return;
      }

      const { error } = await supabase.auth.signUp({ email, password });
      if (error) throw error;
      setMessage("Account created. Check your email if confirmation is enabled, then sign in.");
      setMode("signin");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_15%_20%,#dbeafe,transparent_35%),radial-gradient(circle_at_85%_10%,#fef3c7,transparent_35%),#f8fafc] flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white/90 backdrop-blur shadow-xl p-6">
        <h1 className="text-2xl font-semibold tracking-tight mb-1">Portfolio Tracker</h1>
        <p className="text-sm text-slate-600 mb-6">Sign in to access your holdings dashboard.</p>

        <div className="inline-flex rounded-xl bg-slate-100 p-1 mb-5">
          <button
            onClick={() => setMode("signin")}
            className={`px-4 py-2 text-sm rounded-lg transition ${
              mode === "signin" ? "bg-slate-900 text-white" : "text-slate-600"
            }`}
          >
            Sign In
          </button>
          <button
            onClick={() => setMode("signup")}
            className={`px-4 py-2 text-sm rounded-lg transition ${
              mode === "signup" ? "bg-slate-900 text-white" : "text-slate-600"
            }`}
          >
            Register
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-500"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-500"
              placeholder="••••••••"
            />
          </div>

          {message ? <p className="text-sm text-slate-700 rounded-lg bg-slate-100 px-3 py-2">{message}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-slate-900 text-white py-2.5 font-medium hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? "Please wait..." : mode === "signin" ? "Sign In" : "Create Account"}
          </button>
        </form>
      </div>
    </main>
  );
}

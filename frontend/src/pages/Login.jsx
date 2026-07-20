import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ORIGIN } from "../lib/api";
import { useAuth } from "../lib/auth";
import { toast } from "sonner";
import { ArrowLeft, ArrowUpRight } from "@phosphor-icons/react";

function formatErr(detail) {
  if (!detail) return "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

const GOOGLE_ERROR_MESSAGES = {
  oauth_state_mismatch: "That sign-in attempt expired -- please try again.",
  google_token_exchange_failed: "Google sign-in failed -- please try again.",
  google_profile_fetch_failed: "Couldn't fetch your Google profile -- please try again.",
  google_email_unverified: "That Google account's email isn't verified -- please use a verified account.",
};

export default function Login() {
  const [mode, setMode] = useState("login"); // login | signup
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const refCode = params.get("ref") || (typeof localStorage !== "undefined" ? localStorage.getItem("pending_referral") : null);

  const [mfaToken, setMfaToken] = useState(null);
  const [mfaCode, setMfaCode] = useState("");

  // Landed back here from the Google OAuth redirect -- either an error, or an
  // MFA challenge (Google auth succeeded but a second factor is still needed).
  useEffect(() => {
    const err = params.get("error");
    const mfaFromGoogle = params.get("mfa_token");
    if (err) toast.error(GOOGLE_ERROR_MESSAGES[err] || "Sign-in failed -- please try again.");
    if (mfaFromGoogle) setMfaToken(mfaFromGoogle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setBusy(true);
    try {
      const url = mode === "signup" ? "/auth/signup" : "/auth/login";
      const payload = mode === "signup"
        ? { email: form.email, password: form.password, name: form.name || form.email.split("@")[0], referral_code: refCode || undefined }
        : { email: form.email, password: form.password };
      const { data } = await api.post(url, payload);
      if (data?.mfa_required) {
        setMfaToken(data.mfa_token);
        setBusy(false);
        return;
      }
      if (typeof localStorage !== "undefined") localStorage.removeItem("pending_referral");
      await refresh();
      toast.success(mode === "signup" ? "Account created" : "Welcome back");
      nav("/dashboard", { replace: true });
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail));
    }
    setBusy(false);
  };

  const submitMfa = async (e) => {
    e?.preventDefault?.();
    if (busy || mfaCode.length < 6) return;
    setBusy(true);
    try {
      await api.post("/auth/mfa/verify", { mfa_token: mfaToken, code: mfaCode });
      await refresh();
      toast.success("Welcome back");
      nav("/dashboard", { replace: true });
    } catch (err) {
      toast.error(formatErr(err.response?.data?.detail) || "Incorrect code");
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-background text-foreground grid md:grid-cols-2">
      {/* Left brand panel */}
      <div className="hidden md:block relative overflow-hidden bg-primary">
        <div className="absolute inset-0 grain" />
        <div className="relative h-full flex flex-col justify-between p-12 text-primary-foreground">
          <Link to="/" className="text-sm inline-flex items-center gap-2 hover:text-accent transition-colors"><ArrowLeft size={16} /> Back</Link>
          <div>
            <div className="text-[11px] uppercase tracking-[0.3em] text-accent mb-4">The intelligent front desk</div>
            <h1 className="font-display text-5xl leading-tight">Your business,<br/>always on.</h1>
            <p className="mt-6 max-w-md opacity-80 leading-relaxed">One line of code. A knowledge base built from your website. An AI Employee that grows smarter every week.</p>
          </div>
          <div className="text-xs opacity-60">© {new Date().getFullYear()} AI Employee</div>
        </div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          {mfaToken ? (
            <>
              <div className="font-display text-3xl tracking-tight">Two-factor code</div>
              <p className="text-sm text-muted-foreground mt-2">Enter the 6-digit code from your authenticator app.</p>
              <form onSubmit={submitMfa} className="mt-8 space-y-4">
                <input
                  data-testid="mfa-code" required autoFocus inputMode="numeric" maxLength={6}
                  value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="123456"
                  className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary text-center tracking-[0.4em] text-lg"
                />
                <button type="submit" disabled={busy} data-testid="mfa-submit"
                  className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground py-3 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-60">
                  {busy ? "Verifying…" : "Verify"}
                </button>
                <button type="button" onClick={() => { setMfaToken(null); setMfaCode(""); }} className="w-full text-xs text-muted-foreground hover:text-foreground">
                  Back to login
                </button>
              </form>
            </>
          ) : (
            <>
              <div className="font-display text-3xl tracking-tight">{mode === "signup" ? "Create your account" : "Welcome back"}</div>
              <p className="text-sm text-muted-foreground mt-2">
                {mode === "signup" ? "Free forever plan. No card required." : "Sign in to your AI Employee dashboard."}
              </p>

              <a
                href={`${ORIGIN}/api/auth/google/login`}
                data-testid="google-oauth-btn"
                className="mt-6 w-full flex items-center justify-center gap-2 border border-border bg-card py-3 rounded-md hover:bg-secondary transition-colors text-sm"
              >
                <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
                  <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.1 8 3.1l5.7-5.7C34.6 6.1 29.6 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z"/>
                  <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 15.9 18.9 13 24 13c3.1 0 5.9 1.1 8 3.1l5.7-5.7C34.6 6.1 29.6 4 24 4 16.3 4 9.7 8.4 6.3 14.7z"/>
                  <path fill="#4CAF50" d="M24 44c5.5 0 10.4-1.9 14.3-5.1l-6.6-5.4C29.7 35.4 27 36.3 24 36.3c-5.3 0-9.8-3.4-11.3-8.1l-6.6 5.1C9.5 39.6 16.2 44 24 44z"/>
                  <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.2 4.3-4.1 5.7l6.6 5.4C41.5 36 44 30.6 44 24c0-1.3-.1-2.3-.4-3.5z"/>
                </svg>
                Continue with Google
              </a>

              <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground">
                <div className="flex-1 h-px bg-border" /> or <div className="flex-1 h-px bg-border" />
              </div>

              <form onSubmit={submit} className="space-y-4">
                {mode === "signup" && (
                  <label className="block">
                    <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Name</div>
                    <input data-testid="signup-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                      className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary" />
                  </label>
                )}
                <label className="block">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Email</div>
                  <input type="email" data-testid="auth-email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                    className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary" />
                </label>
                <label className="block">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Password</div>
                    {mode === "login" && <Link to="/forgot-password" className="text-[11px] text-accent hover:underline">Forgot?</Link>}
                  </div>
                  <input type="password" data-testid="auth-password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary" />
                  {mode === "signup" && <div className="text-[11px] text-muted-foreground mt-1">At least 8 characters.</div>}
                </label>

                <button type="submit" disabled={busy} data-testid={`auth-${mode}-submit`}
                  className="mt-2 w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground py-3 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-60">
                  {busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}
                  {!busy && <ArrowUpRight size={16} />}
                </button>
              </form>

              <div className="mt-6 text-sm text-muted-foreground">
                {mode === "signup" ? (
                  <>Already have an account? <button onClick={() => setMode("login")} data-testid="switch-login" className="text-accent hover:underline">Sign in</button></>
                ) : (
                  <>New here? <button onClick={() => setMode("signup")} data-testid="switch-signup" className="text-accent hover:underline">Create an account</button></>
                )}
              </div>

              {refCode && (
                <div className="mt-4 text-xs px-3 py-2 rounded-md bg-accent/10 border border-accent/30">
                  Referral applied: <span className="font-mono">{refCode}</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

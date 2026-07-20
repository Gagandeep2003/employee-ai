import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { ArrowLeft } from "@phosphor-icons/react";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch {
      toast.error("Something went wrong -- please try again.");
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-8">
      <div className="w-full max-w-sm">
        <Link to="/login" className="text-sm inline-flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8">
          <ArrowLeft size={16} /> Back to login
        </Link>
        <div className="font-display text-3xl tracking-tight">Reset your password</div>
        {sent ? (
          <p className="text-sm text-muted-foreground mt-4">
            If an account exists for <span className="text-foreground">{email}</span>, we've sent a reset link -- check your inbox.
          </p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground mt-2">Enter your email and we'll send a reset link.</p>
            <form onSubmit={submit} className="mt-8 space-y-4">
              <input
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                data-testid="forgot-email" placeholder="you@business.com"
                className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary"
              />
              <button type="submit" disabled={busy} data-testid="forgot-submit"
                className="w-full bg-primary text-primary-foreground py-3 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-60">
                {busy ? "Sending…" : "Send reset link"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

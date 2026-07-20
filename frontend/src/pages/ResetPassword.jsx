import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { ArrowLeft } from "@phosphor-icons/react";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (busy || !token) return;
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      toast.success("Password updated -- sign in with your new password.");
      nav("/login", { replace: true });
    } catch (err) {
      toast.error(err.response?.data?.detail || "That link may have expired -- request a new one.");
    }
    setBusy(false);
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-8">
        <div className="text-center">
          <div className="font-display text-2xl">Missing reset link</div>
          <Link to="/forgot-password" className="text-accent hover:underline text-sm mt-2 inline-block">Request a new one</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-8">
      <div className="w-full max-w-sm">
        <Link to="/login" className="text-sm inline-flex items-center gap-2 text-muted-foreground hover:text-foreground mb-8">
          <ArrowLeft size={16} /> Back to login
        </Link>
        <div className="font-display text-3xl tracking-tight">Set a new password</div>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <input
            type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
            data-testid="reset-password" placeholder="New password"
            className="w-full px-3 py-2.5 rounded-md border border-border bg-card outline-none focus:ring-2 focus:ring-primary"
          />
          <div className="text-[11px] text-muted-foreground">At least 8 characters.</div>
          <button type="submit" disabled={busy} data-testid="reset-submit"
            className="w-full bg-primary text-primary-foreground py-3 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-60">
            {busy ? "Saving…" : "Update password"}
          </button>
        </form>
      </div>
    </div>
  );
}

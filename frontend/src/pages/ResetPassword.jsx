import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { ArrowLeft, LockKey, CheckCircle } from "@phosphor-icons/react";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (busy || !token) return;
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    if (password !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      toast.success("Password updated successfully! Redirecting to sign in...");
      setTimeout(() => nav("/login", { replace: true }), 1500);
    } catch (err) {
      toast.error(err.response?.data?.detail || "That link may have expired -- request a new one.");
    }
    setBusy(false);
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-amber-50 flex items-center justify-center p-8">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
            <LockKey size={40} className="text-red-600" weight="fill" />
          </div>
          <h1 className="font-display text-2xl font-bold text-gray-900 mb-3">Invalid Reset Link</h1>
          <p className="text-gray-600 mb-6">This password reset link is missing or has already been used.</p>
          <Link to="/forgot-password" className="inline-flex items-center gap-2 text-emerald-600 hover:text-emerald-700 font-medium">
            <ArrowLeft size={16} /> Request a new reset link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-amber-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Link to="/login" className="text-sm inline-flex items-center gap-2 text-muted-foreground hover:text-foreground mb-6 transition-colors">
          <ArrowLeft size={16} /> Back to login
        </Link>
        
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
          <div className="bg-gradient-to-r from-emerald-600 to-teal-600 px-8 py-6">
            <div className="flex items-center gap-3 text-white mb-2">
              <LockKey size={32} weight="fill" />
              <h1 className="font-display text-2xl font-bold">Set New Password</h1>
            </div>
            <p className="text-emerald-100 text-sm">Create a strong password for your account</p>
          </div>

          <div className="p-8">
            <form onSubmit={submit} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">New Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="reset-password"
                  aria-label="New password"
                  placeholder="At least 8 characters"
                  className="w-full px-4 py-3 rounded-lg border border-gray-200 bg-white outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Confirm Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  data-testid="reset-confirm-password"
                  aria-label="Confirm password"
                  placeholder="Re-enter your password"
                  className="w-full px-4 py-3 rounded-lg border border-gray-200 bg-white outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                />
              </div>

              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <CheckCircle size={20} className="text-emerald-600 shrink-0 mt-0.5" weight="fill" />
                  <div className="text-sm text-emerald-800">
                    <p className="font-medium mb-1">Password requirements:</p>
                    <ul className="list-disc list-inside space-y-1 text-emerald-700">
                      <li>At least 8 characters long</li>
                      <li>Use a mix of letters, numbers, and symbols</li>
                      <li>Avoid common passwords or personal information</li>
                    </ul>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={busy || password.length < 8 || password !== confirmPassword}
                data-testid="reset-submit"
                className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 text-white py-3.5 rounded-lg hover:from-emerald-700 hover:to-teal-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium shadow-lg shadow-emerald-500/25"
              >
                {busy ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                    Updating password...
                  </span>
                ) : "Update Password"}
              </button>
            </form>
          </div>
        </div>

        <p className="text-xs text-center text-gray-500 mt-6">
          For security, this link will expire after use or in 24 hours.
        </p>
      </div>
    </div>
  );
}

import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { ArrowLeft, EnvelopeSimple, ShieldCheck } from "@phosphor-icons/react";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [step, setStep] = useState("email");
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const navigate = useNavigate();
  
  const requestOtp = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/auth/forgot-password", { email });
      setSessionId(data.session_id);
      setStep("otp");
      toast.success("OTP sent to your email!");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Something went wrong -- please try again.");
    }
    setBusy(false);
  };

  const verifyOtpAndReset = async (e) => {
    e.preventDefault();
    if (busy || !sessionId) return;
    const otpCode = otp.join("");
    if (otpCode.length !== 6) {
      toast.error("Please enter the complete 6-digit OTP");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/reset-password-otp", { 
        session_id: sessionId, 
        otp: otpCode,
        new_password: newPassword 
      });
      toast.success("Password updated successfully! Please sign in.");
      navigate("/login");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Invalid or expired OTP. Please try again.");
    }
    setBusy(false);
  };

  const handleOtpChange = (index, value) => {
    if (!/^\d*$/.test(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);
    if (value && index < 5) {
      document.getElementById(`otp-${index + 1}`)?.focus();
    }
  };

  const handleOtpKeyDown = (index, e) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      document.getElementById(`otp-${index - 1}`)?.focus();
    }
  };

  const resendOtp = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setOtp(["", "", "", "", "", ""]);
      toast.success("New OTP sent!");
    } catch {
      toast.error("Failed to resend OTP");
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-amber-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Link to="/login" className="text-sm inline-flex items-center gap-2 text-muted-foreground hover:text-foreground mb-6 transition-colors">
          <ArrowLeft size={16} /> Back to login
        </Link>
        
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
          <div className="bg-gradient-to-r from-emerald-600 to-teal-600 px-8 py-6">
            <div className="flex items-center gap-3 text-white mb-2">
              <ShieldCheck size={32} weight="fill" />
              <h1 className="font-display text-2xl font-bold">Secure Password Reset</h1>
            </div>
            <p className="text-emerald-100 text-sm">Verify your identity with a one-time code</p>
          </div>

          <div className="p-8">
            {step === "email" && (
              <div className="space-y-6">
                <div className="text-center">
                  <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <EnvelopeSimple size={32} className="text-emerald-600" weight="fill" />
                  </div>
                  <h2 className="font-display text-xl font-semibold text-gray-900">Enter your email</h2>
                  <p className="text-sm text-gray-600 mt-2">We'll send a 6-digit verification code to your email address</p>
                </div>
                
                <form onSubmit={requestOtp} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Email Address</label>
                    <input
                      type="email" 
                      required 
                      value={email} 
                      onChange={(e) => setEmail(e.target.value)}
                      data-testid="forgot-email" 
                      aria-label="Email address" 
                      placeholder="you@business.com"
                      className="w-full px-4 py-3 rounded-lg border border-gray-200 bg-white outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                    />
                  </div>
                  <button 
                    type="submit" 
                    disabled={busy || !email} 
                    data-testid="forgot-submit"
                    className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 text-white py-3.5 rounded-lg hover:from-emerald-700 hover:to-teal-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium shadow-lg shadow-emerald-500/25"
                  >
                    {busy ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                        Sending code...
                      </span>
                    ) : "Send Verification Code"}
                  </button>
                </form>
              </div>
            )}

            {step === "otp" && (
              <div className="space-y-6">
                <div className="text-center">
                  <h2 className="font-display text-xl font-semibold text-gray-900">Enter verification code</h2>
                  <p className="text-sm text-gray-600 mt-2">
                    We sent a 6-digit code to <span className="font-medium text-gray-900">{email}</span>
                  </p>
                </div>
                
                <form onSubmit={verifyOtpAndReset} className="space-y-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-3 text-center">One-Time Password</label>
                    <div className="flex justify-center gap-2">
                      {otp.map((digit, index) => (
                        <input
                          key={index}
                          id={`otp-${index}`}
                          type="text"
                          inputMode="numeric"
                          maxLength={1}
                          value={digit}
                          onChange={(e) => handleOtpChange(index, e.target.value)}
                          onKeyDown={(e) => handleOtpKeyDown(index, e)}
                          className="w-12 h-14 text-center text-2xl font-bold border-2 border-gray-200 rounded-lg focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none transition-all"
                        />
                      ))}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">New Password</label>
                      <input
                        type="password"
                        required
                        minLength={8}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
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
                        placeholder="Re-enter your password"
                        className="w-full px-4 py-3 rounded-lg border border-gray-200 bg-white outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                      />
                    </div>
                  </div>

                  <button 
                    type="submit" 
                    disabled={busy || otp.some(d => !d) || newPassword.length < 8} 
                    className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 text-white py-3.5 rounded-lg hover:from-emerald-700 hover:to-teal-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium shadow-lg shadow-emerald-500/25"
                  >
                    {busy ? "Resetting password..." : "Reset Password"}
                  </button>

                  <div className="text-center">
                    <button
                      type="button"
                      onClick={resendOtp}
                      disabled={busy}
                      className="text-sm text-emerald-600 hover:text-emerald-700 font-medium disabled:opacity-50"
                    >
                      Didn't receive the code? Resend
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        </div>

        <p className="text-xs text-center text-gray-500 mt-6">
          For security, the verification code expires in 15 minutes and can only be used once.
        </p>
      </div>
    </div>
  );
}

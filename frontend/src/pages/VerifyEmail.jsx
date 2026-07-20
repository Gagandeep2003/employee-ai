import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState("checking"); // checking | ok | error

  useEffect(() => {
    if (!token) { setStatus("error"); return; }
    api.post("/auth/verify-email", { token })
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-8">
      <div className="text-center max-w-sm">
        {status === "checking" && <div className="text-sm text-muted-foreground">Verifying…</div>}
        {status === "ok" && (
          <>
            <div className="font-display text-2xl">Email verified</div>
            <p className="text-sm text-muted-foreground mt-2">You're all set.</p>
            <Link to="/dashboard" className="text-accent hover:underline text-sm mt-4 inline-block">Go to dashboard</Link>
          </>
        )}
        {status === "error" && (
          <>
            <div className="font-display text-2xl">Link expired or invalid</div>
            <p className="text-sm text-muted-foreground mt-2">You can request a new verification email from your dashboard.</p>
            <Link to="/dashboard" className="text-accent hover:underline text-sm mt-4 inline-block">Go to dashboard</Link>
          </>
        )}
      </div>
    </div>
  );
}

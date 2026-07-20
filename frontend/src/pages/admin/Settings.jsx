import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { toast } from "sonner";
import { H1, Card, Btn } from "./_ui";

const LABELS = {
  default_free_limit: { l: "Free plan chat limit", n: true },
  starter_limit: { l: "Starter plan limit", n: true },
  pro_limit: { l: "Pro plan limit", n: true },
  referral_discount_pct: { l: "Referral discount %", n: true },
  referral_months: { l: "Referral duration (months)", n: true },
  confidence_threshold: { l: "AI confidence threshold (0-1)", n: true, step: 0.05 },
  max_upload_mb: { l: "Max upload size (MB)", n: true },
  crawl_max_pages: { l: "Crawler max pages", n: true },
  watermark_required_on_free: { l: "Force 'Powered by' on free plan", b: true },
  maintenance_mode: { l: "Maintenance mode (blocks widget chat)", b: true },
};

function MfaCard() {
  const { user, refresh } = useAuth();
  const [setup, setSetup] = useState(null); // { secret, provisioning_uri }
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const startSetup = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/mfa/setup");
      setSetup(data);
    } catch { toast.error("Couldn't start MFA setup"); }
    setBusy(false);
  };

  const confirmSetup = async () => {
    setBusy(true);
    try {
      await api.post("/admin/mfa/enable", { code });
      toast.success("Two-factor authentication enabled");
      setSetup(null); setCode("");
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || "Incorrect code"); }
    setBusy(false);
  };

  const disable = async () => {
    setBusy(true);
    try {
      await api.post("/admin/mfa/disable", { password });
      toast.success("Two-factor authentication disabled");
      setPassword("");
      await refresh();
    } catch (e) { toast.error(e.response?.data?.detail || "Incorrect password"); }
    setBusy(false);
  };

  return (
    <Card title="Two-factor authentication">
      <div className="p-4 space-y-3">
        <p className="text-sm text-muted-foreground">
          Admin accounts can impersonate any business owner -- strongly recommend enabling this.
        </p>
        {user?.mfa_enabled ? (
          <div className="flex items-center gap-3">
            <span className="text-xs px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">Enabled</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Confirm password to disable"
              data-testid="mfa-disable-password" className="text-sm px-3 py-1.5 rounded-md border border-border bg-background" />
            <Btn variant="danger" onClick={disable} disabled={busy || !password} testid="mfa-disable-btn">Disable</Btn>
          </div>
        ) : setup ? (
          <div className="space-y-3">
            <div className="text-sm">Scan this in your authenticator app, or enter the key manually:</div>
            <div className="font-mono text-xs bg-secondary p-3 rounded-md break-all" data-testid="mfa-secret">{setup.secret}</div>
            <div className="text-xs text-muted-foreground break-all">{setup.provisioning_uri}</div>
            <div className="flex items-center gap-2">
              <input
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} maxLength={6}
                placeholder="6-digit code" data-testid="mfa-confirm-code"
                className="text-sm px-3 py-1.5 rounded-md border border-border bg-background w-32 text-center tracking-widest"
              />
              <Btn onClick={confirmSetup} disabled={busy || code.length < 6} testid="mfa-confirm-btn">Confirm & enable</Btn>
              <button onClick={() => { setSetup(null); setCode(""); }} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
            </div>
          </div>
        ) : (
          <Btn onClick={startSetup} disabled={busy} testid="mfa-setup-btn">Set up two-factor authentication</Btn>
        )}
      </div>
    </Card>
  );
}

export default function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/admin/settings").then(({ data }) => setS(data)); }, []);
  const save = async () => {
    try { await api.put("/admin/settings", s); toast.success("Settings saved"); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  if (!s) return <div className="p-8">Loading…</div>;
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Platform defaults" title="Settings">
        <Btn onClick={save}>Save changes</Btn>
      </H1>
      <MfaCard />
      <Card>
        <div className="divide-y divide-border">
          {Object.entries(LABELS).map(([k, cfg]) => (
            <div key={k} className="p-4 flex items-center justify-between gap-4">
              <div>
                <div className="font-medium">{cfg.l}</div>
                <div className="text-xs text-muted-foreground font-mono">{k}</div>
              </div>
              {cfg.b ? (
                <button onClick={() => setS({ ...s, [k]: !s[k] })}
                  className={`relative w-12 h-6 rounded-full transition-colors ${s[k] ? "bg-accent" : "bg-secondary"}`}>
                  <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${s[k] ? "translate-x-6" : "translate-x-0.5"}`} />
                </button>
              ) : (
                <input type="number" step={cfg.step || 1} value={s[k]} onChange={(e) => setS({ ...s, [k]: cfg.step ? parseFloat(e.target.value) : parseInt(e.target.value) })}
                  className="w-32 px-3 py-2 rounded-md border border-border bg-background text-sm text-right font-mono" />
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

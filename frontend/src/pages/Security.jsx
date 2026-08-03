import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { useMfa } from "../lib/useMfa";
import { toast } from "sonner";
import {
  ShieldCheck, Key, Trash, ArrowClockwise, Copy,
  SignOut, DeviceMobile, Monitor, WarningCircle, CheckCircle, Plus,
} from "@phosphor-icons/react";

function relativeTime(iso) {
  if (!iso) return "never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function CardShell({ title, subtitle, action, children }) {
  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="p-4 border-b border-border flex items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground font-medium">{title}</div>
          {subtitle && <div className="text-sm text-muted-foreground mt-0.5">{subtitle}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
function SecurityScoreCard({ overview }) {
  if (!overview) {
    return (
      <CardShell title="Security posture">
        <div className="p-4 text-sm text-muted-foreground">Loading…</div>
      </CardShell>
    );
  }
  const score = overview.score ?? 0;
  const color = score >= 75 ? "text-emerald-600" : score >= 50 ? "text-amber-600" : "text-destructive";
  return (
    <CardShell title="Security posture">
      <div className="p-4 flex items-start gap-6">
        <div className="flex flex-col items-center justify-center shrink-0 w-20">
          <div className={`text-3xl font-display ${color}`}>{score}</div>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">out of 100</div>
        </div>
        <div className="flex-1 space-y-2">
          {(overview.checklist || []).map((c) => (
            <div key={c.key} className="flex items-center gap-2 text-sm">
              {c.ok ? <CheckCircle size={16} weight="fill" className="text-emerald-500 shrink-0" /> : <WarningCircle size={16} weight="fill" className="text-amber-500 shrink-0" />}
              <span className={c.ok ? "" : "text-muted-foreground"}>{c.label}</span>
            </div>
          ))}
        </div>
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
function TwoFactorCard() {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const { user, setup, busy, startSetup, confirmSetup, disable, cancelSetup } = useMfa("/auth/mfa");

  return (
    <CardShell title="Two-factor authentication" subtitle="Require a code from your authenticator app at sign-in.">
      <div className="p-4">
        {user?.mfa_enabled ? (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-600 border border-emerald-500/30 inline-flex items-center gap-1">
              <ShieldCheck size={14} weight="fill" /> Enabled
            </span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="Confirm password to disable" aria-label="Confirm password to disable two-factor authentication"
              data-testid="owner-mfa-disable-password"
              className="text-sm px-3 py-1.5 rounded-md border border-border bg-background" />
            <button onClick={async () => { if (await disable(password)) setPassword(""); }} disabled={busy || !password}
              data-testid="owner-mfa-disable-btn"
              className="text-sm px-3 py-1.5 rounded-md border border-destructive/40 text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50">
              Disable
            </button>
          </div>
        ) : setup ? (
          <div className="space-y-3">
            <div className="text-sm">Scan this in your authenticator app, or enter the key manually:</div>
            <div className="font-mono text-xs bg-secondary p-3 rounded-md break-all">{setup.secret}</div>
            <div className="flex items-center gap-2">
              <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} maxLength={6}
                placeholder="6-digit code" aria-label="Six-digit authenticator code" data-testid="owner-mfa-confirm-code"
                className="text-sm px-3 py-1.5 rounded-md border border-border bg-background w-32 text-center tracking-widest" />
              <button onClick={async () => { if (await confirmSetup(code)) setCode(""); }} disabled={busy || code.length < 6}
                data-testid="owner-mfa-confirm-btn"
                className="text-sm px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50">
                Confirm & enable
              </button>
              <button onClick={cancelSetup} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
            </div>
          </div>
        ) : (
          <button onClick={startSetup} disabled={busy} data-testid="owner-mfa-setup-btn"
            className="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-secondary transition-colors disabled:opacity-50">
            Set up two-factor authentication
          </button>
        )}
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
function SessionsCard({ sessions, onChange }) {
  const [busyId, setBusyId] = useState(null);

  if (sessions === null) {
    return (
      <CardShell title="Active sessions">
        <div className="p-8 text-sm text-muted-foreground text-center">Loading…</div>
      </CardShell>
    );
  }

  const revoke = async (id) => {
    setBusyId(id);
    try {
      await api.delete(`/auth/sessions/${id}`);
      toast.success("Device signed out");
      onChange();
    } catch { toast.error("Couldn't sign out that device"); }
    setBusyId(null);
  };

  const revokeOthers = async () => {
    try {
      await api.post("/auth/sessions/revoke-all", { include_current: false });
      toast.success("Signed out of all other devices");
      onChange();
    } catch { toast.error("Couldn't sign out other devices"); }
  };

  return (
    <CardShell title="Active sessions" subtitle={`${sessions.length} device${sessions.length === 1 ? "" : "s"} signed in`}
      action={sessions.length > 1 && (
        <button onClick={revokeOthers} data-testid="revoke-all-sessions"
          className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-secondary transition-colors inline-flex items-center gap-1.5">
          <SignOut size={14} /> Sign out other devices
        </button>
      )}>
      <div className="divide-y divide-border">
        {sessions.map((s) => (
          <div key={s.id} className="p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              {/Chrome \(iOS\)|Firefox \(iOS\)|iOS|Android/.test(s.device_name) ? <DeviceMobile size={20} className="text-muted-foreground shrink-0" /> : <Monitor size={20} className="text-muted-foreground shrink-0" />}
              <div className="min-w-0">
                <div className="text-sm font-medium flex items-center gap-2">
                  {s.device_name}
                  {s.current && <span className="text-[10px] px-1.5 py-0.5 rounded border border-accent text-accent">This device</span>}
                </div>
                <div className="text-xs text-muted-foreground truncate">{s.ip || "unknown IP"} · active {relativeTime(s.last_used_at)}</div>
              </div>
            </div>
            {!s.current && (
              <button onClick={() => revoke(s.id)} disabled={busyId === s.id} data-testid={`revoke-session-${s.id}`}
                className="text-xs px-2.5 py-1.5 rounded-md border border-border hover:border-destructive/40 hover:text-destructive transition-colors shrink-0 disabled:opacity-50">
                Sign out
              </button>
            )}
          </div>
        ))}
        {!sessions.length && <div className="p-8 text-sm text-muted-foreground text-center">No active sessions.</div>}
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
const OUTCOME_STYLE = {
  success: ["Signed in", "text-emerald-600 border-emerald-500/30 bg-emerald-500/10"],
  failed_password: ["Wrong password", "text-destructive border-destructive/30 bg-destructive/10"],
  locked: ["Account locked", "text-destructive border-destructive/30 bg-destructive/10"],
  mfa_required: ["Password OK, 2FA required", "text-amber-600 border-amber-500/30 bg-amber-500/10"],
  mfa_failed: ["Wrong 2FA code", "text-destructive border-destructive/30 bg-destructive/10"],
};

function LoginHistoryCard({ events }) {
  if (events === null) {
    return (
      <CardShell title="Login history" subtitle="Recent sign-in attempts on your account">
        <div className="p-8 text-sm text-muted-foreground text-center">Loading…</div>
      </CardShell>
    );
  }
  return (
    <CardShell title="Login history" subtitle="Recent sign-in attempts on your account">
      <div className="divide-y divide-border max-h-80 overflow-y-auto">
        {events.map((e) => {
          const [label, cls] = OUTCOME_STYLE[e.outcome] || [e.outcome, "text-muted-foreground border-border"];
          return (
            <div key={e.id} className="p-3 flex items-center justify-between gap-4 text-sm">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${cls}`}>{label}</span>
                <span className="text-muted-foreground truncate">{e.device_name} · {e.ip || "unknown IP"}</span>
              </div>
              <span className="text-xs text-muted-foreground shrink-0">{relativeTime(e.created_at)}</span>
            </div>
          );
        })}
        {!events.length && <div className="p-8 text-sm text-muted-foreground text-center">No login history yet.</div>}
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
const SCOPE_LABELS = {
  "business:read": "Read business profile",
  "appointments:read": "Read appointments",
  "appointments:write": "Create/cancel appointments",
  "conversations:read": "Read conversations",
  "analytics:read": "Read analytics",
};

function NewKeyForm({ businessId, scopes, onCreated, onCancel }) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);

  const toggle = (s) => setSelected((cur) => cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]);

  const create = async () => {
    if (!name.trim() || !selected.length) return;
    setBusy(true);
    try {
      const { data } = await api.post("/api-keys", { business_id: businessId, name: name.trim(), scopes: selected });
      onCreated(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Couldn't create API key");
    }
    setBusy(false);
  };

  return (
    <div className="p-4 space-y-3 bg-secondary/40">
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Zapier integration"
        aria-label="API key name" data-testid="new-key-name" className="w-full text-sm px-3 py-2 rounded-md border border-border bg-background" />
      <div className="flex flex-wrap gap-2">
        {scopes.map((s) => (
          <button key={s} type="button" onClick={() => toggle(s)} data-testid={`scope-${s}`} aria-pressed={selected.includes(s)}
            className={`text-xs px-2.5 py-1.5 rounded-md border transition-colors ${selected.includes(s) ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-secondary"}`}>
            {SCOPE_LABELS[s] || s}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <button onClick={create} disabled={busy || !name.trim() || !selected.length} data-testid="create-key-submit"
          className="text-sm px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50">
          Create key
        </button>
        <button onClick={onCancel} className="text-xs text-muted-foreground hover:text-foreground">Cancel</button>
      </div>
    </div>
  );
}

function RevealedSecret({ apiKey, onDone }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(apiKey.secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="p-4 space-y-3 bg-amber-500/10 border-b border-amber-500/30">
      <div className="text-sm font-medium flex items-center gap-2"><WarningCircle size={16} className="text-amber-600" weight="fill" /> Copy this key now -- it won't be shown again</div>
      <div className="flex items-center gap-2">
        <code className="flex-1 text-xs bg-background border border-border rounded-md px-3 py-2 break-all">{apiKey.secret}</code>
        <button onClick={copy} data-testid="copy-key-secret" className="text-xs px-2.5 py-2 rounded-md border border-border hover:bg-secondary transition-colors inline-flex items-center gap-1 shrink-0">
          <Copy size={14} /> {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <button onClick={onDone} className="text-xs text-muted-foreground hover:text-foreground">Done</button>
    </div>
  );
}

function ApiKeysCard({ businessId }) {
  const [keys, setKeys] = useState(null);
  const [scopes, setScopes] = useState([]);
  const [creating, setCreating] = useState(false);
  const [revealed, setRevealed] = useState(null);

  const load = () => {
    if (!businessId) return;
    api.get("/api-keys", { params: { business_id: businessId } }).then(({ data }) => setKeys(data));
  };
  useEffect(load, [businessId]);
  useEffect(() => { api.get("/api-keys/scopes").then(({ data }) => setScopes(data.scopes)); }, []);

  const rotate = async (id) => {
    try {
      const { data } = await api.post(`/api-keys/${id}/rotate`);
      setRevealed(data);
      load();
    } catch { toast.error("Couldn't rotate key"); }
  };

  const revoke = async (id) => {
    try {
      await api.delete(`/api-keys/${id}`);
      toast.success("API key revoked");
      load();
    } catch { toast.error("Couldn't revoke key"); }
  };

  if (keys === null) return null;

  return (
    <CardShell title="API keys" subtitle="Let your own systems call the AI Employee API on this business's behalf."
      action={!creating && (
        <button onClick={() => setCreating(true)} data-testid="new-key-btn"
          className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-secondary transition-colors inline-flex items-center gap-1.5">
          <Plus size={14} /> New key
        </button>
      )}>
      {revealed && <RevealedSecret apiKey={revealed} onDone={() => setRevealed(null)} />}
      {creating && (
        <NewKeyForm businessId={businessId} scopes={scopes}
          onCreated={(data) => { setRevealed(data); setCreating(false); load(); }}
          onCancel={() => setCreating(false)} />
      )}
      <div className="divide-y divide-border">
        {keys.map((k) => (
          <div key={k.id} className="p-4 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="text-sm font-medium flex items-center gap-2">
                <Key size={16} className="text-muted-foreground shrink-0" />
                {k.name}
                {k.status === "revoked" && <span className="text-[10px] px-1.5 py-0.5 rounded border border-destructive/30 text-destructive">Revoked</span>}
              </div>
              <div className="text-xs text-muted-foreground font-mono mt-0.5">{k.key_prefix}...</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {k.scopes.map((s) => SCOPE_LABELS[s] || s).join(", ")} · last used {relativeTime(k.last_used_at)}
              </div>
            </div>
            {k.status === "active" && (
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => rotate(k.id)} data-testid={`rotate-key-${k.id}`} title="Rotate" aria-label={`Rotate key ${k.name}`}
                  className="text-xs p-2 rounded-md border border-border hover:bg-secondary transition-colors">
                  <ArrowClockwise size={14} />
                </button>
                <button onClick={() => revoke(k.id)} data-testid={`revoke-key-${k.id}`} title="Revoke" aria-label={`Revoke key ${k.name}`}
                  className="text-xs p-2 rounded-md border border-border hover:border-destructive/40 hover:text-destructive transition-colors">
                  <Trash size={14} />
                </button>
              </div>
            )}
          </div>
        ))}
        {!keys.length && !creating && <div className="p-8 text-sm text-muted-foreground text-center">No API keys yet -- create one to let your own tools call the API.</div>}
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------------------
export default function Security() {
  const { current } = useBiz();
  const [overview, setOverview] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [history, setHistory] = useState(null);

  const load = () => {
    api.get("/auth/security-overview").then(({ data }) => setOverview(data));
    api.get("/auth/sessions").then(({ data }) => setSessions(data));
    api.get("/auth/login-history").then(({ data }) => setHistory(data));
  };
  useEffect(load, []);

  return (
    <div className="p-8 space-y-6 max-w-4xl">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Settings</div>
        <h1 className="font-display text-4xl tracking-tight">Security</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage how you sign in, which devices are trusted, and who else can call your account's API.</p>
      </div>

      <SecurityScoreCard overview={overview} />
      <TwoFactorCard />
      <SessionsCard sessions={sessions} onChange={load} />
      <LoginHistoryCard events={history} />
      {current && <ApiKeysCard businessId={current.business_id} />}
    </div>
  );
}

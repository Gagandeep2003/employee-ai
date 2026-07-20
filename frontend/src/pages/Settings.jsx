import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Clock } from "@phosphor-icons/react";

function daysAgo(iso) {
  if (!iso) return null;
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d;
}

function QuickFacts({ businessId }) {
  const [facts, setFacts] = useState(null);
  const [saving, setSaving] = useState(false);

  const refresh = () => api.get(`/businesses/${businessId}/quick-facts`).then(({ data }) => setFacts(data));
  useEffect(() => { if (businessId) refresh(); }, [businessId]);

  if (!facts) return null;
  const age = daysAgo(facts.updated_at);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put(`/businesses/${businessId}/quick-facts`, {
        hours_note: facts.hours_note, special_or_promo: facts.special_or_promo, announcement: facts.announcement,
      });
      setFacts(data);
      toast.success("Quick facts saved -- your AI knows immediately");
    } catch { toast.error("Save failed"); }
    setSaving(false);
  };

  return (
    <div className="bg-card border border-border rounded-lg p-6 space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground flex items-center gap-2">
          <Clock size={12} /> Quick facts
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          The fastest way to keep your AI current. These override anything older in your knowledge base --
          no re-crawl needed. {age !== null && (
            <span className={age > 30 ? "text-accent" : ""}>
              {age === 0 ? "Updated today." : `Last updated ${age} day${age === 1 ? "" : "s"} ago.`}
            </span>
          )}
        </p>
      </div>
      <label className="block">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Today's hours (if different from usual)</div>
        <input value={facts.hours_note} onChange={(e) => setFacts({ ...facts, hours_note: e.target.value })}
          placeholder="e.g. Open till 9pm today" data-testid="qf-hours"
          className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
      </label>
      <label className="block">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Current special or promo</div>
        <input value={facts.special_or_promo} onChange={(e) => setFacts({ ...facts, special_or_promo: e.target.value })}
          placeholder="e.g. 20% off all shirts this weekend" data-testid="qf-promo"
          className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
      </label>
      <label className="block">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Announcement (closures, changes, etc.)</div>
        <input value={facts.announcement} onChange={(e) => setFacts({ ...facts, announcement: e.target.value })}
          placeholder="e.g. Closed Dec 25-26 for the holidays" data-testid="qf-announcement"
          className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
      </label>
      <button onClick={save} disabled={saving} data-testid="qf-save"
        className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors text-sm disabled:opacity-60">
        {saving ? "Saving…" : "Save quick facts"}
      </button>
      <div className="text-[11px] text-muted-foreground">
        Tip: you can also just tell your AI assistant on the dashboard -- "we're closed tomorrow" updates this automatically.
      </div>
    </div>
  );
}

export default function Settings() {
  const { current, refresh } = useBiz();
  const [f, setF] = useState(null);
  useEffect(() => { if (current) setF({ ...current }); }, [current]);
  if (!f) return null;
  const save = async () => {
    try {
      await api.patch(`/businesses/${current.business_id}`, {
        name: f.name, website: f.website, email: f.email, phone: f.phone,
        category: f.category, country: f.country, language: f.language, timezone: f.timezone,
      });
      await refresh();
      toast.success("Saved");
    } catch { toast.error("Save failed"); }
  };
  return (
    <div className="p-8 space-y-6 max-w-3xl">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Settings</div>
        <h1 className="font-display text-4xl tracking-tight">Business profile.</h1>
      </div>
      <div className="grid md:grid-cols-2 gap-4 bg-card border border-border rounded-lg p-6">
        {["name","website","email","phone","category","country","language","timezone"].map(k => (
          <label key={k} className="block">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">{k}</div>
            <input value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`settings-${k}`} className="w-full px-3 py-2 rounded-md border border-border bg-background" />
          </label>
        ))}
      </div>
      <button onClick={save} data-testid="settings-save" className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors">Save</button>

      <QuickFacts businessId={current.business_id} />
    </div>
  );
}

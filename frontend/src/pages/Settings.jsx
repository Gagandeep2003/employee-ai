import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Clock, Quotes, Plus, Trash } from "@phosphor-icons/react";

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

function Testimonials({ businessId }) {
  const [items, setItems] = useState(null);
  const [draft, setDraft] = useState({ quote: "", author: "", role: "" });
  const [saving, setSaving] = useState(false);

  const refresh = () => api.get(`/businesses/${businessId}/testimonials`).then(({ data }) => setItems(data));
  useEffect(() => { if (businessId) refresh(); }, [businessId]);

  if (items === null) return null;

  const save = async (next) => {
    setSaving(true);
    try {
      const { data } = await api.put(`/businesses/${businessId}/testimonials`, { testimonials: next });
      setItems(data);
    } catch { toast.error("Couldn't save testimonials"); }
    setSaving(false);
  };

  const add = () => {
    if (!draft.quote.trim() || !draft.author.trim()) return;
    const next = [...items, { quote: draft.quote.trim(), author: draft.author.trim(), role: draft.role.trim() || null }];
    save(next);
    setDraft({ quote: "", author: "", role: "" });
  };

  const remove = (i) => save(items.filter((_, idx) => idx !== i));

  return (
    <div className="bg-card border border-border rounded-lg p-6 space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground flex items-center gap-2">
          <Quotes size={12} /> Testimonials
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Real customer quotes shown on your public chat page. Only what you add here appears -- nothing is made up.
        </p>
      </div>
      <div className="space-y-2">
        {items.map((t, i) => (
          <div key={i} className="flex items-start justify-between gap-3 bg-secondary rounded-md px-3 py-2">
            <div className="text-sm">
              <div className="italic">"{t.quote}"</div>
              <div className="text-xs text-muted-foreground mt-1">{t.author}{t.role ? ` · ${t.role}` : ""}</div>
            </div>
            <button onClick={() => remove(i)} aria-label={`Remove testimonial from ${t.author}`} data-testid={`remove-testimonial-${i}`} className="text-muted-foreground hover:text-destructive shrink-0"><Trash size={14} /></button>
          </div>
        ))}
        {!items.length && <div className="text-sm text-muted-foreground">No testimonials yet.</div>}
      </div>
      <div className="grid sm:grid-cols-3 gap-2">
        <input value={draft.quote} onChange={(e) => setDraft({ ...draft, quote: e.target.value })} placeholder="What did they say?"
          aria-label="Testimonial quote" data-testid="new-testimonial-quote" className="sm:col-span-3 px-3 py-2 rounded-md border border-border bg-background text-sm" />
        <input value={draft.author} onChange={(e) => setDraft({ ...draft, author: e.target.value })} placeholder="Customer name"
          aria-label="Customer name" data-testid="new-testimonial-author" className="px-3 py-2 rounded-md border border-border bg-background text-sm" />
        <input value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })} placeholder="Role (optional)"
          aria-label="Customer role (optional)" className="px-3 py-2 rounded-md border border-border bg-background text-sm" />
        <button onClick={add} disabled={saving} data-testid="add-testimonial" className="px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm flex items-center justify-center gap-1"><Plus size={14} /> Add</button>
      </div>
    </div>
  );
}

const COMMON_TIMEZONES = [
  "UTC", "Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Asia/Tokyo", "Asia/Shanghai",
  "Asia/Karachi", "Asia/Dhaka", "Asia/Jakarta", "Asia/Bangkok", "Asia/Kuala_Lumpur",
  "Asia/Riyadh", "Asia/Kathmandu", "Asia/Colombo", "Europe/London", "Europe/Paris",
  "Europe/Berlin", "Europe/Madrid", "Europe/Rome", "Europe/Moscow", "Africa/Cairo",
  "Africa/Lagos", "Africa/Johannesburg", "America/New_York", "America/Chicago",
  "America/Denver", "America/Los_Angeles", "America/Toronto", "America/Sao_Paulo",
  "America/Mexico_City", "Australia/Sydney", "Australia/Melbourne", "Pacific/Auckland",
];

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
    } catch (e) {
      toast.error(e.response?.data?.detail?.[0]?.msg || e.response?.data?.detail || "Save failed");
    }
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
            <input value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`settings-${k}`}
              list={k === "timezone" ? "timezone-options" : undefined}
              placeholder={k === "timezone" ? "e.g. Asia/Kolkata" : undefined}
              className="w-full px-3 py-2 rounded-md border border-border bg-background" />
          </label>
        ))}
        <datalist id="timezone-options">
          {COMMON_TIMEZONES.map((tz) => <option key={tz} value={tz} />)}
        </datalist>
      </div>
      <button onClick={save} data-testid="settings-save" className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors">Save</button>

      <QuickFacts businessId={current.business_id} />
      <Testimonials businessId={current.business_id} />
    </div>
  );
}

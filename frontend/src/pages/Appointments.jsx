import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Plus, Trash, ToggleLeft, ToggleRight, Sparkle, X, Check, CalendarX } from "@phosphor-icons/react";

const DAYS = [
  ["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"],
  ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"],
];

const EMPTY_SETTINGS = {
  enabled: false,
  services: [],
  working_hours: Object.fromEntries(DAYS.map(([k]) => [k, null])),
  slot_interval_minutes: 30,
  holidays: [],
};

function DraftReviewCard({ businessId, onResolved }) {
  const [draft, setDraft] = useState(undefined); // undefined = loading, null = none
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/businesses/${businessId}/appointments/settings/draft`).then(({ data }) => setDraft(data));
  }, [businessId]);

  const publish = async () => {
    setBusy(true);
    try {
      await api.post(`/businesses/${businessId}/appointments/settings/publish-draft`);
      toast.success("Applied -- appointment booking is now live using what we found");
      setDraft(null);
      onResolved();
    } catch { toast.error("Couldn't publish"); }
    setBusy(false);
  };

  const dismiss = async () => {
    setBusy(true);
    try {
      await api.delete(`/businesses/${businessId}/appointments/settings/draft`);
      setDraft(null);
    } catch { toast.error("Couldn't dismiss"); }
    setBusy(false);
  };

  if (!draft) return null;
  const openDays = DAYS.filter(([k]) => draft.working_hours?.[k]);

  return (
    <div className="rounded-lg border border-accent/40 bg-accent/5 p-6 space-y-3" data-testid="appointment-draft-card">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Sparkle size={16} weight="fill" className="text-accent" />
        We found possible appointment hours on your website
        {draft.confidence && <span className="text-[10px] px-1.5 py-0.5 rounded border border-accent text-accent uppercase">{draft.confidence} confidence</span>}
      </div>
      <div className="text-sm space-y-1">
        {openDays.length ? openDays.map(([k, label]) => (
          <div key={k} className="text-muted-foreground">{label}: <span className="text-foreground">{draft.working_hours[k][0]}-{draft.working_hours[k][1]}</span></div>
        )) : <div className="text-muted-foreground">No specific hours detected.</div>}
        {draft.services?.length > 0 && (
          <div className="text-muted-foreground">Services: <span className="text-foreground">{draft.services.map((s) => s.name).join(", ")}</span></div>
        )}
        {draft.holidays?.length > 0 && (
          <div className="text-muted-foreground">Holidays: <span className="text-foreground">{draft.holidays.join(", ")}</span></div>
        )}
        {draft.timezone_guess && <div className="text-muted-foreground">Timezone guess: <span className="text-foreground">{draft.timezone_guess}</span></div>}
      </div>
      <div className="text-xs text-muted-foreground">Review this carefully -- nothing changes until you publish it. You can edit hours below afterward.</div>
      <div className="flex gap-2">
        <button onClick={publish} disabled={busy} data-testid="publish-draft" className="text-sm px-3 py-1.5 rounded-md bg-accent text-accent-foreground hover:opacity-90 transition-opacity disabled:opacity-50 inline-flex items-center gap-1.5">
          <Check size={14} /> Looks right, use it
        </button>
        <button onClick={dismiss} disabled={busy} data-testid="dismiss-draft" className="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-secondary transition-colors inline-flex items-center gap-1.5">
          <X size={14} /> Not accurate, dismiss
        </button>
      </div>
    </div>
  );
}

export default function Appointments() {
  const { current } = useBiz();
  const [settings, setSettings] = useState(EMPTY_SETTINGS);
  const [appointments, setAppointments] = useState([]);
  const [saving, setSaving] = useState(false);
  const [newService, setNewService] = useState({ name: "", duration_minutes: 30 });
  const [newHoliday, setNewHoliday] = useState("");

  const refresh = () => {
    if (!current) return;
    api.get(`/businesses/${current.business_id}/appointments/settings`).then(({ data }) => setSettings({ holidays: [], ...data }));
    api.get(`/businesses/${current.business_id}/appointments`).then(({ data }) => setAppointments(data));
  };
  useEffect(refresh, [current]);

  const save = async (next) => {
    setSaving(true);
    try {
      const { data } = await api.put(`/businesses/${current.business_id}/appointments/settings`, next);
      setSettings({ holidays: [], ...data });
      toast.success("Appointment settings saved");
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    setSaving(false);
  };

  const toggleEnabled = () => save({ ...settings, enabled: !settings.enabled });

  const addService = () => {
    if (!newService.name.trim()) return;
    const next = { ...settings, services: [...settings.services, { ...newService, name: newService.name.trim() }] };
    setSettings(next);
    setNewService({ name: "", duration_minutes: 30 });
    save(next);
  };

  const removeService = (name) => {
    const next = { ...settings, services: settings.services.filter((s) => s.name !== name) };
    save(next);
  };

  const setDayHours = (day, open, close) => {
    const next = { ...settings, working_hours: { ...settings.working_hours, [day]: open && close ? [open, close] : null } };
    setSettings(next);
  };

  const addHoliday = () => {
    if (!newHoliday || settings.holidays.includes(newHoliday)) return;
    const next = { ...settings, holidays: [...settings.holidays, newHoliday].sort() };
    setSettings(next);
    setNewHoliday("");
    save(next);
  };

  const removeHoliday = (date) => save({ ...settings, holidays: settings.holidays.filter((h) => h !== date) });

  const cancelAppointment = async (id) => {
    try {
      await api.post(`/businesses/${current.business_id}/appointments/${id}/cancel`);
      toast.success("Appointment cancelled");
      refresh();
    } catch { toast.error("Failed to cancel"); }
  };

  if (!current) return null;

  return (
    <div className="p-8 space-y-6 max-w-4xl">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Appointments</div>
        <h1 className="font-display text-4xl tracking-tight">Let the AI book your calendar.</h1>
        <p className="text-sm text-muted-foreground mt-2">
          Turn this on and your AI Employee can check availability and book appointments for customers directly in
          the chat -- no back-and-forth calls. Good fit for clinics, salons, consultants, and repair shops.
        </p>
      </div>

      <DraftReviewCard businessId={current.business_id} onResolved={refresh} />

      <div className="bg-card border border-border rounded-lg p-6 flex items-center justify-between">
        <div>
          <div className="font-medium">Appointment booking</div>
          <div className="text-sm text-muted-foreground">{settings.enabled ? "Customers can book directly in chat" : "Currently off -- the AI will only answer questions"}</div>
        </div>
        <button onClick={toggleEnabled} disabled={saving} aria-label="Appointment booking" aria-pressed={settings.enabled} data-testid="appointments-toggle" className="text-accent">
          {settings.enabled ? <ToggleRight size={36} weight="fill" /> : <ToggleLeft size={36} />}
        </button>
      </div>

      <div className="bg-card border border-border rounded-lg p-6 space-y-4">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Services</div>
        <div className="space-y-2">
          {settings.services.length === 0 && <div className="text-sm text-muted-foreground">No services yet -- add one below.</div>}
          {settings.services.map((s) => (
            <div key={s.name} className="flex items-center justify-between bg-secondary rounded-md px-3 py-2 text-sm">
              <span>{s.name} <span className="text-muted-foreground">· {s.duration_minutes} min</span></span>
              <button onClick={() => removeService(s.name)} aria-label={`Remove ${s.name}`} data-testid={`remove-service-${s.name}`} className="text-muted-foreground hover:text-destructive"><Trash size={14} /></button>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={newService.name}
            onChange={(e) => setNewService((s) => ({ ...s, name: e.target.value }))}
            placeholder="e.g. Consultation"
            aria-label="Service name"
            data-testid="new-service-name"
            className="flex-1 px-3 py-2 rounded-md border border-border bg-background text-sm"
          />
          <input
            type="number" min={5} max={480} step={5}
            value={newService.duration_minutes}
            onChange={(e) => setNewService((s) => ({ ...s, duration_minutes: parseInt(e.target.value, 10) || 30 }))}
            aria-label="Duration in minutes"
            className="w-24 px-3 py-2 rounded-md border border-border bg-background text-sm"
          />
          <button onClick={addService} data-testid="add-service" className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm flex items-center gap-1"><Plus size={14} /> Add</button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg p-6 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Working hours</div>
          <div className="text-xs text-muted-foreground">Timezone: <span className="text-foreground font-medium">{current.timezone || "UTC"}</span> · change it in Settings</div>
        </div>
        {DAYS.map(([key, label]) => {
          const hours = settings.working_hours?.[key];
          return (
            <div key={key} className="flex items-center gap-3 text-sm">
              <div className="w-28 text-foreground/80">{label}</div>
              <input type="time" value={hours?.[0] || ""} onChange={(e) => setDayHours(key, e.target.value, hours?.[1] || "17:00")}
                aria-label={`${label} opening time`} data-testid={`hours-${key}-open`} className="px-2 py-1 rounded-md border border-border bg-background" />
              <span className="text-muted-foreground">to</span>
              <input type="time" value={hours?.[1] || ""} onChange={(e) => setDayHours(key, hours?.[0] || "09:00", e.target.value)}
                aria-label={`${label} closing time`} data-testid={`hours-${key}-close`} className="px-2 py-1 rounded-md border border-border bg-background" />
              {hours && <button onClick={() => setDayHours(key, null, null)} className="text-xs text-muted-foreground hover:text-destructive">Closed</button>}
            </div>
          );
        })}
        <button onClick={() => save(settings)} disabled={saving} data-testid="save-hours" className="mt-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm">
          Save working hours
        </button>
      </div>

      <div className="bg-card border border-border rounded-lg p-6 space-y-3">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Holidays & closures</div>
        <p className="text-xs text-muted-foreground">Specific dates you're closed regardless of your normal weekly hours -- public holidays, a planned closure, etc.</p>
        <div className="flex flex-wrap gap-2">
          {settings.holidays.map((h) => (
            <span key={h} className="text-xs px-2 py-1 rounded-md bg-secondary flex items-center gap-1.5">
              <CalendarX size={12} /> {h}
              <button onClick={() => removeHoliday(h)} aria-label={`Remove holiday ${h}`} data-testid={`remove-holiday-${h}`} className="text-muted-foreground hover:text-destructive"><X size={11} /></button>
            </span>
          ))}
          {!settings.holidays.length && <span className="text-sm text-muted-foreground">No holidays added.</span>}
        </div>
        <div className="flex gap-2">
          <input type="date" value={newHoliday} onChange={(e) => setNewHoliday(e.target.value)}
            aria-label="New holiday date" data-testid="new-holiday-date" className="px-3 py-2 rounded-md border border-border bg-background text-sm" />
          <button onClick={addHoliday} data-testid="add-holiday" className="px-4 py-2 rounded-md border border-border hover:bg-secondary transition-colors text-sm flex items-center gap-1"><Plus size={14} /> Add</button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg p-6">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-3">Upcoming appointments</div>
        {appointments.length === 0 && <div className="text-sm text-muted-foreground">No upcoming appointments yet.</div>}
        <div className="space-y-2">
          {appointments.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-secondary rounded-md px-3 py-2 text-sm">
              <div>
                <div className="font-medium">{a.service} -- {a.customer_name}</div>
                <div className="text-muted-foreground text-xs">
                  {new Date(a.start_time).toLocaleString()} · {a.customer_phone || a.customer_email || "no contact given"} · Ref {a.reference}
                </div>
              </div>
              <button onClick={() => cancelAppointment(a.id)} data-testid={`cancel-appt-${a.id}`} className="text-xs text-muted-foreground hover:text-destructive">Cancel</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

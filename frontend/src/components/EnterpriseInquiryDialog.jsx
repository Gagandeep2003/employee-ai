import React, { useState, useEffect } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "./ui/dialog";

/** Enterprise is deliberately not a self-serve checkout tier -- "custom pricing" means a
 * real conversation (volume, SLAs, contract terms), so this just captures the lead and
 * hands it to a human. See POST /billing/enterprise-inquiry. */
export default function EnterpriseInquiryDialog({ open, onOpenChange, businessId, defaultName, defaultEmail, defaultBusinessName }) {
  const [form, setForm] = useState({ name: "", email: "", business_name: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  // This dialog is mounted once and toggled via `open`, not remounted per-open -- so the
  // defaults (owner name/email/business) usually aren't loaded yet at mount time. Re-seed
  // from the latest props each time it actually opens, instead of only once at mount.
  useEffect(() => {
    if (open) {
      setForm({ name: defaultName || "", email: defaultEmail || "", business_name: defaultBusinessName || "", message: "" });
      setSent(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.business_name.trim()) return;
    setBusy(true);
    try {
      await api.post("/billing/enterprise-inquiry", { ...form, business_id: businessId || null });
      setSent(true);
    } catch {
      toast.error("Couldn't send that -- please try again in a moment.");
    }
    setBusy(false);
  };

  const close = (next) => onOpenChange(next);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        {sent ? (
          <div className="py-4 text-center space-y-2">
            <DialogTitle>Thanks -- we'll be in touch.</DialogTitle>
            <DialogDescription>Usually within a business day. In the meantime, feel free to keep using the app on your current plan.</DialogDescription>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Tell us about your needs</DialogTitle>
              <DialogDescription>Enterprise pricing is tailored to your volume and requirements -- no fixed catalog price. Share a few details and we'll follow up.</DialogDescription>
            </DialogHeader>
            <form onSubmit={submit} className="space-y-3">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Your name" aria-label="Your name" required data-testid="ent-name"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
              <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="Work email" aria-label="Work email" required data-testid="ent-email"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
              <input value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })}
                placeholder="Business name" aria-label="Business name" required data-testid="ent-business"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
              <textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder="What are you looking for? (volume, integrations, timeline...)" aria-label="What are you looking for"
                rows={3} data-testid="ent-message"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
              <button type="submit" disabled={busy} data-testid="ent-submit"
                className="w-full py-2.5 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50">
                {busy ? "Sending…" : "Send"}
              </button>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { toast } from "sonner";
import { CheckCircle, DownloadSimple, WarningCircle } from "@phosphor-icons/react";
import EnterpriseInquiryDialog from "../components/EnterpriseInquiryDialog";

function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

function rupees(paise) {
  return `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function GstDetailsCard({ businessId }) {
  const [details, setDetails] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get(`/billing/gst-details/${businessId}`).then(({ data }) => setDetails(data));
  }, [businessId]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/billing/gst-details/${businessId}`, {
        gst_state_code: details.gst_state_code || null,
        gstin: details.gstin || null,
        billing_legal_name: details.billing_legal_name || null,
        billing_address: details.billing_address || null,
      });
      toast.success("GST details saved");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Couldn't save GST details");
    }
    setSaving(false);
  };

  if (!details) return null;

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="p-4 border-b border-border">
        <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">GST details</div>
        <div className="text-sm text-muted-foreground mt-1">Used on your invoices. Add your state to get an accurate CGST/SGST vs IGST split.</div>
      </div>
      <div className="p-4 grid sm:grid-cols-2 gap-3">
        <select value={details.gst_state_code || ""} onChange={(e) => setDetails({ ...details, gst_state_code: e.target.value })}
          aria-label="GST state" data-testid="gst-state" className="px-3 py-2 rounded-md border border-border bg-background text-sm">
          <option value="">Select state…</option>
          {Object.entries(details.state_options || {}).sort((a, b) => a[1].localeCompare(b[1])).map(([code, name]) => (
            <option key={code} value={code}>{name}</option>
          ))}
        </select>
        <input placeholder="GSTIN (optional)" value={details.gstin || ""} onChange={(e) => setDetails({ ...details, gstin: e.target.value.toUpperCase() })}
          aria-label="GSTIN" data-testid="gst-gstin" className="px-3 py-2 rounded-md border border-border bg-background text-sm font-mono" />
        <input placeholder="Billing legal name" value={details.billing_legal_name || ""} onChange={(e) => setDetails({ ...details, billing_legal_name: e.target.value })}
          aria-label="Billing legal name" className="px-3 py-2 rounded-md border border-border bg-background text-sm" />
        <input placeholder="Billing address" value={details.billing_address || ""} onChange={(e) => setDetails({ ...details, billing_address: e.target.value })}
          aria-label="Billing address" className="px-3 py-2 rounded-md border border-border bg-background text-sm" />
      </div>
      <div className="px-4 pb-4">
        <button onClick={save} disabled={saving} data-testid="save-gst-details"
          className="text-sm px-4 py-2 rounded-md border border-border hover:bg-secondary transition-colors disabled:opacity-50">
          {saving ? "Saving…" : "Save GST details"}
        </button>
      </div>
    </div>
  );
}

export default function Billing() {
  const { current, refresh } = useBiz();
  const { user } = useAuth();
  const [plans, setPlans] = useState({});
  const [invoices, setInvoices] = useState([]);
  const [processing, setProcessing] = useState(null);
  const [showEnterprise, setShowEnterprise] = useState(false);

  const refreshInvoices = () => {
    if (current) api.get(`/billing/invoices/${current.business_id}`).then(({ data }) => setInvoices(data));
  };

  useEffect(() => {
    api.get("/billing/plans").then(({ data }) => setPlans(data));
    refreshInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);

  const subscribe = async (plan) => {
    if (!current || current.plan === plan) return;
    setProcessing(plan);
    try {
      const { data } = await api.post("/billing/subscribe", { business_id: current.business_id, plan });

      if (!data.requires_payment) {
        await refresh();
        refreshInvoices();
        if (data.scheduled_plan_change) {
          toast.success(`Switching to ${plans[data.scheduled_plan_change]?.name || data.scheduled_plan_change} at the end of your current period (${new Date(data.effective_at).toLocaleDateString()})`);
        } else {
          toast.success(`Switched to ${plans[plan]?.name || plan}`);
        }
        setProcessing(null);
        return;
      }

      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded) {
        toast.error("Couldn't load the payment form -- check your connection and try again.");
        setProcessing(null);
        return;
      }

      const rzp = new window.Razorpay({
        key: data.key_id,
        amount: data.amount,
        currency: data.currency,
        name: data.business_name || "Roviq Ai",
        description: data.proration_applied ? `${plans[plan]?.name || plan} plan (prorated upgrade)` : `${plans[plan]?.name || plan} plan`,
        order_id: data.order_id,
        theme: { color: "#1E3F33" },
        handler: async (response) => {
          try {
            await api.post("/billing/verify", {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            await refresh();
            refreshInvoices();
            toast.success(`Payment received -- you're on ${plans[plan]?.name || plan} now`);
          } catch {
            toast.error("Payment went through, but we couldn't confirm it automatically -- contact support with your payment ID.");
          }
          setProcessing(null);
        },
        modal: { ondismiss: () => setProcessing(null) },
      });
      rzp.on("payment.failed", () => {
        toast.error("Payment failed -- please try again.");
        setProcessing(null);
      });
      rzp.open();
    } catch (e) {
      if (e?.response?.status === 503) {
        toast.error("Payments aren't set up on this deployment yet -- contact the site owner.");
      } else {
        toast.error("Couldn't start checkout, please try again.");
      }
      setProcessing(null);
    }
  };

  const cancelSubscription = async (immediate) => {
    const msg = immediate
      ? "Cancel immediately and drop to the free plan right now?"
      : "Cancel? You'll keep your current plan until the end of this billing period, then move to the free plan.";
    if (!window.confirm(msg)) return;
    try {
      await api.post("/billing/cancel", { business_id: current.business_id, immediate });
      await refresh();
      toast.success(immediate ? "Moved to the free plan" : "Your plan will end at the current period's close");
    } catch {
      toast.error("Couldn't cancel -- please try again");
    }
  };

  const downloadInvoice = async (inv) => {
    try {
      const res = await api.get(`/billing/invoices/${current.business_id}/${inv.id}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = `${inv.invoice_number}.pdf`; a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error("Couldn't download invoice");
    }
  };

  if (!current) return null;

  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Billing</div>
        <h1 className="font-display text-4xl tracking-tight">Current plan: <span className="text-accent">{current.plan}</span></h1>
        <div className="text-sm text-muted-foreground mt-2">Usage: {current.monthly_used} / {current.monthly_limit} chats this month</div>
        {current.current_period_end && (
          <div className="text-sm text-muted-foreground mt-1">
            {current.cancel_at_period_end
              ? `Ends ${new Date(current.current_period_end).toLocaleDateString()} -- moving to free plan`
              : current.pending_plan_change
              ? `Switching to ${plans[current.pending_plan_change]?.name || current.pending_plan_change} on ${new Date(current.current_period_end).toLocaleDateString()}`
              : `Renews around ${new Date(current.current_period_end).toLocaleDateString()}`}
          </div>
        )}
        {current.subscription_status === "past_due" && (
          <div className="mt-3 flex items-center gap-2 text-sm px-3 py-2 rounded-md border border-amber-500/40 bg-amber-500/10 text-amber-700 w-fit">
            <WarningCircle size={16} weight="fill" />
            Payment needed -- renew soon to keep your plan{current.grace_period_ends_at ? ` (grace period ends ${new Date(current.grace_period_ends_at).toLocaleDateString()})` : ""}.
          </div>
        )}
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Object.entries(plans).map(([k, p]) => {
          const isCurrent = current.plan === k || (current.plan === "pro" && k === "growth"); // "pro" is the old name for "growth"
          return (
          <div key={k} className={`rounded-lg p-6 border ${isCurrent ? "border-accent bg-accent/5" : "border-border bg-card"}`}>
            <div className="font-display text-2xl">{p.name}</div>
            <div className="mt-3 font-display text-4xl">₹{p.price_inr}<span className="text-base opacity-60">/mo</span></div>
            {p.price_inr > 0 && <div className="text-xs text-muted-foreground mt-1">Inclusive of GST</div>}
            <ul className="mt-5 space-y-2 text-sm">
              {p.features.map((f) => <li key={f} className="flex gap-2"><CheckCircle size={14} weight="fill" className="text-accent mt-0.5" /> {f}</li>)}
            </ul>
            <button onClick={() => subscribe(k)} disabled={isCurrent || processing === k} data-testid={`sub-${k}`} className="mt-6 w-full py-2.5 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50">
              {isCurrent ? "Current plan" : processing === k ? "Opening checkout…" : `Choose ${p.name}`}
            </button>
          </div>
        )})}
      </div>
      <p className="text-xs text-muted-foreground">Need more than Scale? <button onClick={() => setShowEnterprise(true)} data-testid="open-enterprise" className="underline hover:text-foreground">Contact us about Enterprise</button>.</p>

      {current.plan !== "free" && !current.cancel_at_period_end && (
        <div className="flex gap-2">
          <button onClick={() => cancelSubscription(false)} data-testid="cancel-at-period-end"
            className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-secondary transition-colors">
            Cancel at period end
          </button>
          <button onClick={() => cancelSubscription(true)} data-testid="cancel-immediate"
            className="text-xs px-3 py-1.5 rounded-md border border-destructive/30 text-destructive hover:bg-destructive/10 transition-colors">
            Cancel immediately
          </button>
        </div>
      )}

      <GstDetailsCard businessId={current.business_id} />

      <div className="bg-card border border-border rounded-lg">
        <div className="p-4 border-b border-border text-xs uppercase tracking-[0.2em] text-muted-foreground">Invoices</div>
        <div className="divide-y divide-border">
          {invoices.map((i) => (
            <div key={i.id} className="p-4 flex justify-between items-center text-sm gap-3">
              <div className="min-w-0">
                <div className="font-mono">{i.invoice_number}</div>
                <div className="text-muted-foreground text-xs">{new Date(i.created_at).toLocaleString()}</div>
                {i.is_intra_state ? (
                  <div className="text-[11px] text-muted-foreground">Taxable {rupees(i.taxable_value_paise)} + CGST {rupees(i.cgst_paise)} + SGST {rupees(i.sgst_paise)}</div>
                ) : (
                  <div className="text-[11px] text-muted-foreground">Taxable {rupees(i.taxable_value_paise)} + IGST {rupees(i.igst_paise)}</div>
                )}
              </div>
              <div className="text-right shrink-0">
                <div>{rupees(i.total_paise)} · {i.plan}</div>
                <div className={`text-xs ${i.status === "refunded" ? "text-destructive" : i.status === "due" ? "text-amber-600" : "text-accent"}`}>
                  {i.status}{i.refund_amount_paise > 0 && i.status !== "refunded" ? ` (${rupees(i.refund_amount_paise)} refunded)` : ""}
                </div>
              </div>
              <button onClick={() => downloadInvoice(i)} title="Download PDF" aria-label={`Download invoice ${i.invoice_number} as PDF`} data-testid={`download-invoice-${i.id}`}
                className="p-2 rounded-md border border-border hover:bg-secondary transition-colors shrink-0">
                <DownloadSimple size={14} />
              </button>
            </div>
          ))}
          {!invoices.length && <div className="p-6 text-sm text-muted-foreground text-center">No invoices yet.</div>}
        </div>
      </div>

      <EnterpriseInquiryDialog
        open={showEnterprise}
        onOpenChange={setShowEnterprise}
        businessId={current?.business_id}
        defaultName={user?.name}
        defaultEmail={user?.email}
        defaultBusinessName={current?.name}
      />
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { CheckCircle } from "@phosphor-icons/react";

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

export default function Billing() {
  const { current, refresh } = useBiz();
  const [plans, setPlans] = useState({});
  const [invoices, setInvoices] = useState([]);
  const [processing, setProcessing] = useState(null);

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
        // Free plan -- applied instantly, no checkout needed.
        await refresh();
        refreshInvoices();
        toast.success(`Switched to ${plans[plan]?.name || plan}`);
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
        name: data.business_name || "AI Employee",
        description: `${plans[plan]?.name || plan} plan`,
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

  if (!current) return null;

  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Billing</div>
        <h1 className="font-display text-4xl tracking-tight">Current plan: <span className="text-accent">{current.plan}</span></h1>
        <div className="text-sm text-muted-foreground mt-2">Usage: {current.monthly_used} / {current.monthly_limit} chats this month</div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {Object.entries(plans).map(([k, p]) => (
          <div key={k} className={`rounded-lg p-6 border ${current.plan === k ? "border-accent bg-accent/5" : "border-border bg-card"}`}>
            <div className="font-display text-2xl">{p.name}</div>
            <div className="mt-3 font-display text-4xl">₹{p.price_inr}<span className="text-base opacity-60">/mo</span></div>
            <ul className="mt-5 space-y-2 text-sm">
              {p.features.map((f) => <li key={f} className="flex gap-2"><CheckCircle size={14} weight="fill" className="text-accent mt-0.5" /> {f}</li>)}
            </ul>
            <button onClick={() => subscribe(k)} disabled={current.plan === k || processing === k} data-testid={`sub-${k}`} className="mt-6 w-full py-2.5 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50">
              {current.plan === k ? "Current plan" : processing === k ? "Opening checkout…" : `Choose ${p.name}`}
            </button>
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-lg">
        <div className="p-4 border-b border-border text-xs uppercase tracking-[0.2em] text-muted-foreground">Invoices</div>
        <div className="divide-y divide-border">
          {invoices.map((i) => (
            <div key={i.id} className="p-4 flex justify-between text-sm">
              <div>
                <div className="font-mono">{i.id}</div>
                <div className="text-muted-foreground text-xs">{new Date(i.created_at).toLocaleString()}</div>
              </div>
              <div className="text-right">
                <div>₹{i.amount_inr} · {i.plan}</div>
                <div className="text-xs text-accent">{i.status}</div>
              </div>
            </div>
          ))}
          {!invoices.length && <div className="p-6 text-sm text-muted-foreground text-center">No invoices yet.</div>}
        </div>
      </div>
    </div>
  );
}

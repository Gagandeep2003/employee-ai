import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Copy } from "@phosphor-icons/react";

export default function Referrals() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/referrals/mine").then(({ data }) => setD(data)); }, []);
  if (!d) return <div className="p-8">Loading…</div>;
  const link = `${window.location.origin}/?ref=${d.referral_code}`;
  const copy = () => { navigator.clipboard.writeText(link); toast.success("Link copied"); };
  return (
    <div className="p-8 space-y-6 max-w-3xl">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Referrals</div>
        <h1 className="font-display text-4xl tracking-tight">Share the front desk.</h1>
        <p className="text-muted-foreground mt-2">When someone signs up and subscribes through your link, you get 25% off your subscription for 12 months.</p>
      </div>
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Your link</div>
        <div className="flex gap-2 items-center">
          <div className="flex-1 bg-secondary px-3 py-2 rounded-md font-mono text-xs truncate">{link}</div>
          <button onClick={copy} data-testid="copy-ref" className="px-3 py-2 rounded-md border border-border hover:bg-secondary transition-colors flex items-center gap-2"><Copy size={14} /> Copy</button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-lg p-5"><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Invited</div><div className="font-display text-3xl mt-2">{d.invited}</div></div>
        <div className="bg-card border border-border rounded-lg p-5"><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Rewarded</div><div className="font-display text-3xl mt-2">{d.rewarded}</div></div>
        <div className="bg-card border border-border rounded-lg p-5"><div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Discount active</div><div className="font-display text-3xl mt-2">{d.discount_pct}%</div></div>
      </div>
    </div>
  );
}

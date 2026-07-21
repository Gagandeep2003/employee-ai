import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import ChatWidget from "../components/ChatWidget";

/**
 * Full-page hosted chat — a shareable link (QR / Instagram bio / WhatsApp)
 * for owners who don't have a website or can't edit HTML.
 */
export default function TalkPage() {
  const { businessId } = useParams();
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get(`/chat/business/${businessId}/widget-config`)
      .then(({ data }) => { if (!cancelled) setConfig(data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [businessId]);

  if (error) {
    // Previously a failed fetch here just left the page stuck on "Loading…"
    // forever with no explanation. If you're seeing THIS message instead of
    // your actual site, the fetch reached the app but failed -- check that
    // the business id in the URL is correct and hasn't been deleted. If
    // instead you're seeing your hosting platform's own 404/error page (not
    // this one), that's a separate, more common issue: see the note about
    // SPA rewrite rules below.
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-white bg-[#0d1a15] p-6 text-center gap-2">
        <div className="font-display text-2xl">This page isn't available right now.</div>
        <div className="text-sm opacity-70 max-w-sm">
          The link may be out of date, or the business behind it may no longer exist. If you're the
          business owner, check the link in your Widget settings.
        </div>
      </div>
    );
  }

  if (!config) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading…</div>;

  const primary = config.widget?.primary_color || "#1E3F33";
  const accent = config.widget?.accent_color || "#C4A47C";

  return (
    <div className="min-h-screen relative" style={{ background: `linear-gradient(180deg, ${primary} 0%, #0d1a15 100%)` }}>
      <div className="absolute inset-0 grain opacity-40" />
      <div className="relative max-w-2xl mx-auto px-6 pt-14 pb-40 text-white">
        <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: accent }}>AI Employee</div>
        <h1 className="font-display text-4xl md:text-5xl tracking-tight mt-2">{config.business_name}</h1>
        <p className="mt-4 opacity-80 max-w-lg leading-relaxed">
          Chat with our AI receptionist below — she can answer questions about our products, services, hours, prices, policies, and more.
        </p>
        <div className="mt-8 flex flex-wrap gap-2">
          {["Business hours?", "How do I contact you?", "What do you offer?", "Pricing?"].map((s) => (
            <span key={s} className="text-xs px-3 py-1.5 rounded-full border border-white/20 opacity-80">{s}</span>
          ))}
        </div>
        <div className="mt-10 text-xs opacity-60">→ Tap the chat bubble in the bottom-right corner to start.</div>
      </div>
      <ChatWidget businessId={businessId} config={config} />
    </div>
  );
}

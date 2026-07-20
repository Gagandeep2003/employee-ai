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

  useEffect(() => {
    api.get(`/chat/business/${businessId}/widget-config`).then(({ data }) => setConfig(data)).catch(() => {});
  }, [businessId]);

  if (!config) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading…</div>;

  const primary = config.widget.primary_color;
  const accent = config.widget.accent_color;

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

import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import ChatWidget from "../components/ChatWidget";
import {
  PaperPlaneRight, Clock, MapPin, EnvelopeSimple, Phone, CalendarCheck,
  Sparkle, Quotes, CaretDown, GlobeSimple,
} from "@phosphor-icons/react";

const DAY_LABELS = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
const DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function todayKey(timezone) {
  try {
    return new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: timezone }).format(new Date()).slice(0, 3).toLowerCase();
  } catch {
    return DAY_ORDER[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1];
  }
}

// ---------------------------------------------------------------------------
function InlineChat({ businessId, businessName, primary, accent, suggestions }) {
  const [messages, setMessages] = useState([
    { role: "ai", text: `Hi! I'm ${businessName}'s Roviq Ai. Ask me anything -- hours, services, pricing, or booking an appointment.` },
  ]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState(null);
  const [visitorId, setVisitorId] = useState(() => localStorage.getItem(`vis_${businessId}`) || null);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async (textOverride) => {
    const text = (textOverride || input).trim();
    if (!text || sending) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const { data } = await api.post("/chat", { business_id: businessId, message: text, conversation_id: convId, visitor_id: visitorId });
      if (data.conversation_id) setConvId(data.conversation_id);
      if (data.visitor_id) { setVisitorId(data.visitor_id); localStorage.setItem(`vis_${businessId}`, data.visitor_id); }
      setMessages((m) => [...m, { role: "ai", text: data.answer || data.message || "Sorry, something went wrong -- please try again." }]);
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "Sorry, something went wrong on our end -- please try again in a moment." }]);
    }
    setSending(false);
  };

  return (
    <div id="chat" className="rounded-2xl border border-white/15 bg-black/20 backdrop-blur-sm overflow-hidden shadow-2xl">
      <div className="max-h-[420px] overflow-y-auto p-5 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${m.role === "user" ? "rounded-br-sm text-white" : "rounded-bl-sm bg-white/10 text-white/90"}`}
              style={m.role === "user" ? { background: primary } : undefined}
            >
              {m.text}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="px-4 py-2.5 rounded-2xl rounded-bl-sm bg-white/10 flex gap-1">
              {[0, 1, 2].map((i) => <span key={i} className="w-1.5 h-1.5 rounded-full bg-white/50 animate-bounce" style={{ animationDelay: `${i * 0.12}s` }} />)}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {messages.length < 2 && suggestions.length > 0 && (
        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {suggestions.slice(0, 4).map((s) => (
            <button key={s} onClick={() => send(s)} className="text-xs px-3 py-1.5 rounded-full border border-white/20 text-white/80 hover:bg-white/10 transition-colors">
              {s}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-center gap-2 p-3 border-t border-white/10">
        <input
          value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type your question…"
          data-testid="talkpage-chat-input"
          className="flex-1 bg-white/5 border border-white/15 rounded-full px-4 py-2.5 text-sm text-white placeholder:text-white/40 focus:outline-none focus:border-white/30"
        />
        <button type="submit" disabled={sending || !input.trim()} data-testid="talkpage-chat-send"
          className="w-10 h-10 rounded-full flex items-center justify-center text-white disabled:opacity-40 transition-opacity shrink-0"
          style={{ background: accent }}>
          <PaperPlaneRight size={16} weight="fill" />
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
function FaqAccordion({ faqs }) {
  const [open, setOpen] = useState(0);
  return (
    <div className="space-y-2">
      {faqs.map((f, i) => (
        <div key={i} className="border border-white/10 rounded-xl overflow-hidden">
          <button onClick={() => setOpen(open === i ? -1 : i)} data-testid={`faq-toggle-${i}`}
            className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left text-sm font-medium text-white/90 hover:bg-white/5 transition-colors">
            {f.question}
            <CaretDown size={14} className={`shrink-0 transition-transform ${open === i ? "rotate-180" : ""}`} />
          </button>
          {open === i && <div className="px-5 pb-4 text-sm text-white/70 leading-relaxed">{f.answer}</div>}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
export default function TalkPage() {
  const { businessId } = useParams();
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get(`/chat/business/${businessId}/landing-page`)
      .then(({ data }) => { if (!cancelled) setConfig(data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [businessId]);

  useEffect(() => {
    if (!config) return;
    const prevTitle = document.title;
    document.title = `Chat with ${config.business_name}${config.category ? ` — ${config.category}` : ""}`;
    const desc = `Ask ${config.business_name} anything -- hours, services, pricing, or book an appointment, answered instantly by their Roviq Ai.`;
    let meta = document.querySelector('meta[name="description"]');
    const created = !meta;
    if (!meta) { meta = document.createElement("meta"); meta.name = "description"; document.head.appendChild(meta); }
    const prevDesc = meta.content;
    meta.content = desc;
    return () => {
      document.title = prevTitle;
      if (created) meta.remove(); else meta.content = prevDesc;
    };
  }, [config]);

  if (error) {
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

  if (!config) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground bg-[#0d1a15]">Loading…</div>;

  const primary = config.widget?.primary_color || "#1E3F33";
  const accent = config.widget?.accent_color || "#C4A47C";
  const appt = config.appointment_settings || {};
  const today = todayKey(config.timezone);

  const suggestions = [
    ...(appt.enabled ? ["Book an appointment"] : []),
    ...(config.quick_facts?.hours_note ? ["What are your hours?"] : []),
    ...(appt.services || []).slice(0, 2).map((s) => `Tell me about ${s.name}`),
    ...(config.faqs || []).slice(0, 2).map((f) => f.question),
  ].filter(Boolean).slice(0, 4);
  const finalSuggestions = suggestions.length ? suggestions : ["What do you offer?", "What are your hours?", "How do I contact you?"];

  return (
    <div className="min-h-screen relative" style={{ background: `linear-gradient(180deg, ${primary} 0%, #0d1a15 55%)` }}>
      <div className="absolute inset-0 grain opacity-40 pointer-events-none" />

      {/* Hero */}
      <div className="relative max-w-2xl mx-auto px-6 pt-16 pb-10 text-white text-center">
        <div className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.3em] px-3 py-1 rounded-full border border-white/20" style={{ color: accent }}>
          <Sparkle size={11} weight="fill" /> Roviq Ai
        </div>
        <h1 className="font-display text-4xl md:text-5xl tracking-tight mt-4">{config.business_name}</h1>
        {config.category && <p className="mt-2 text-sm text-white/60">{config.category}</p>}
        <p className="mt-4 text-white/80 max-w-lg mx-auto leading-relaxed">
          Ask our AI receptionist anything -- hours, services, pricing, policies{appt.enabled ? ", or book an appointment" : ""} -- answered instantly, day or night.
        </p>
      </div>

      {/* Inline chat */}
      <div className="relative max-w-2xl mx-auto px-6 pb-16">
        <InlineChat businessId={businessId} businessName={config.business_name} primary={primary} accent={accent} suggestions={finalSuggestions} />
      </div>

      {/* Services + hours */}
      {appt.enabled && (appt.services?.length > 0 || Object.values(appt.working_hours || {}).some(Boolean)) && (
        <div className="relative max-w-2xl mx-auto px-6 pb-16 text-white">
          <div className="grid sm:grid-cols-2 gap-6">
            {appt.services?.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.25em] text-white/50 mb-3">Services</div>
                <ul className="space-y-2 text-sm">
                  {appt.services.map((s) => (
                    <li key={s.name} className="flex justify-between border-b border-white/10 pb-2">
                      <span>{s.name}</span><span className="text-white/50">{s.duration_minutes} min</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <div className="text-[10px] uppercase tracking-[0.25em] text-white/50 mb-3 flex items-center gap-1.5"><Clock size={12} /> Hours</div>
              <ul className="space-y-1.5 text-sm">
                {DAY_ORDER.map((d) => (
                  <li key={d} className={`flex justify-between ${d === today ? "text-white font-medium" : "text-white/60"}`}>
                    <span>{DAY_LABELS[d]}{d === today ? " (today)" : ""}</span>
                    <span>{appt.working_hours?.[d] ? `${appt.working_hours[d][0]}-${appt.working_hours[d][1]}` : "Closed"}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <a href="#chat" data-testid="book-cta" className="mt-6 inline-flex items-center gap-2 text-sm px-5 py-2.5 rounded-full text-white transition-transform hover:scale-[1.02]" style={{ background: accent }}>
            <CalendarCheck size={16} weight="fill" /> Book an appointment
          </a>
        </div>
      )}

      {/* FAQ */}
      {config.faqs?.length > 0 && (
        <div className="relative max-w-2xl mx-auto px-6 pb-16 text-white">
          <div className="text-[10px] uppercase tracking-[0.25em] text-white/50 mb-4">Frequently asked</div>
          <FaqAccordion faqs={config.faqs} />
        </div>
      )}

      {/* Testimonials */}
      {config.testimonials?.length > 0 && (
        <div className="relative max-w-2xl mx-auto px-6 pb-16 text-white">
          <div className="text-[10px] uppercase tracking-[0.25em] text-white/50 mb-4">What customers say</div>
          <div className="grid sm:grid-cols-2 gap-4">
            {config.testimonials.map((t, i) => (
              <div key={i} className="rounded-xl border border-white/10 p-5 bg-white/5">
                <Quotes size={18} weight="fill" style={{ color: accent }} />
                <p className="text-sm text-white/85 mt-2 leading-relaxed">{t.quote}</p>
                <div className="text-xs text-white/50 mt-3">{t.author}{t.role ? ` · ${t.role}` : ""}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Contact / footer */}
      <div className="relative max-w-2xl mx-auto px-6 pb-24 text-white/60 text-sm">
        <div className="border-t border-white/10 pt-8 flex flex-wrap gap-x-6 gap-y-2">
          {config.phone && <span className="flex items-center gap-1.5"><Phone size={13} /> {config.phone}</span>}
          {config.email && <span className="flex items-center gap-1.5"><EnvelopeSimple size={13} /> {config.email}</span>}
          {config.website && <a href={config.website} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 hover:text-white transition-colors"><GlobeSimple size={13} /> {config.website.replace(/^https?:\/\//, "")}</a>}
        </div>
        {config.legal_docs?.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/40">
            {config.legal_docs.map((d) => (
              <a key={d.doc_type} href={`/legal/${d.doc_type}`} target="_blank" rel="noreferrer" className="hover:text-white/70 transition-colors">{d.title}</a>
            ))}
          </div>
        )}
      </div>

      <ChatWidget businessId={businessId} config={{ business_name: config.business_name, widget: config.widget, plan: config.plan }} />
    </div>
  );
}

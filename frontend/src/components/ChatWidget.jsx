import React, { useState, useRef, useEffect, useMemo } from "react";
import { PaperPlaneRight, X, ChatCircleDots, User, PaperPlaneTilt } from "@phosphor-icons/react";
import { api } from "../lib/api";

// Respectful-but-playful nudges shown in a teaser bubble before the visitor has
// opened the chat. Never guilt-trips or uses dark-pattern language -- just a
// friendly nudge, shown once per browser session, easily dismissed. Owner-
// configurable: widget.teaser_enabled (default true), widget.teaser_delay_seconds
// (default 4).
const TEASER_LINES = [
  "Psst -- I've got answers. No clicking required \uD83D\uDC4B",
  "Looking for something? Just ask me, I'm faster than digging through menus.",
  "Hey there! I promise I'm more helpful than ten open tabs.",
  "Don't be shy -- I don't judge, I just answer.",
  "Save yourself the scrolling. Ask me anything about us.",
  "I'm the front desk here, minus the hold music.",
  "Got a question? I'm right here, and I don't mind repeating myself.",
];

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

export default function ChatWidget({ businessId, config }) {
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState(null);
  const [visitorId, setVisitorId] = useState(() => localStorage.getItem(`vis_${businessId}`) || null);
  const [loading, setLoading] = useState(false);
  const [handoff, setHandoff] = useState(false);
  const [handoffForm, setHandoffForm] = useState(null); // null | { email: "", note: "" }
  const [teaser, setTeaser] = useState(null);
  const [mounted, setMounted] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const toggleRef = useRef(null);
  const reducedMotion = usePrefersReducedMotion();

  const primary = config?.widget?.primary_color || "#1E3F33";
  const accent = config?.widget?.accent_color || "#C4A47C";
  const welcome = config?.widget?.welcome_message || "Hi! How can I help?";
  const businessName = config?.business_name || "AI Employee";
  const showBranding = config?.widget?.show_branding !== false;
  const teaserEnabled = config?.widget?.teaser_enabled !== false;
  const teaserDelayMs = Math.max(1, Number(config?.widget?.teaser_delay_seconds ?? 4)) * 1000;
  const pulseEnabled = config?.widget?.pulse_enabled !== false;
  const teaserKey = useMemo(() => `ai_employee_teaser_${businessId}`, [businessId]);

  // Widget corner is driven entirely by config -- never hardcoded. Anything
  // other than an explicit "bottom-left" falls back to "bottom-right" so old
  // configs (or a missing value) keep the previous default behavior.
  const position = config?.widget?.position === "bottom-left" ? "bottom-left" : "bottom-right";
  const isBottomLeft = position === "bottom-left";
  const cornerClasses = isBottomLeft ? "left-4 items-start" : "right-4 items-end";
  const teaserTailClass = isBottomLeft ? "rounded-bl-sm" : "rounded-br-sm";
  const teaserCloseClass = isBottomLeft ? "-left-2" : "-right-2";

  // Entrance animation -- the bubble scales/fades in once on first paint, rather
  // than just appearing. Skipped entirely under prefers-reduced-motion.
  useEffect(() => { const t = setTimeout(() => setMounted(true), 50); return () => clearTimeout(t); }, []);

  useEffect(() => {
    if (messages.length === 0) setMessages([{ role: "assistant", text: welcome }]);
  }, [welcome]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: reducedMotion ? "auto" : "smooth" });
  }, [messages, loading, reducedMotion]);

  useEffect(() => {
    if (open) { setEverOpened(true); requestAnimationFrame(() => inputRef.current?.focus()); }
  }, [open]);

  // Escape closes the panel and returns focus to the toggle button -- basic
  // keyboard-accessible modal behavior.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") { setOpen(false); toggleRef.current?.focus(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Show a friendly teaser bubble once per session if the visitor hasn't opened
  // the chat yet -- never repeats within the same session once dismissed or opened.
  // Owner can disable this entirely (widget.teaser_enabled) or tune the delay.
  useEffect(() => {
    if (open || !teaserEnabled) return;
    if (typeof sessionStorage !== "undefined" && sessionStorage.getItem(teaserKey)) return;
    const showTimer = setTimeout(() => {
      setTeaser(TEASER_LINES[Math.floor(Math.random() * TEASER_LINES.length)]);
    }, teaserDelayMs);
    return () => clearTimeout(showTimer);
  }, [open, teaserKey, teaserEnabled, teaserDelayMs]);

  useEffect(() => {
    if (!teaser) return;
    const hideTimer = setTimeout(() => dismissTeaser(), 9000);
    return () => clearTimeout(hideTimer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teaser]);

  // When embedded via <iframe> on a third-party site (see public/embed.js), the
  // iframe itself must be resized as the widget's visual footprint changes --
  // otherwise it either clips the bubble/teaser or blocks clicks on the rest of
  // the host page. We report our footprint any time it changes; embed.js applies
  // it to the iframe's CSS. No-op when not embedded (window.parent === window).
  const reportSize = (w, h) => {
    if (typeof window === "undefined" || window.parent === window) return;
    window.parent.postMessage({ source: "ai-employee-widget", type: "size", width: w, height: h }, "*");
  };

  useEffect(() => {
    if (open) reportSize(392, 600);
    else if (teaser) reportSize(300, 170);
    else reportSize(96, 96);
  }, [open, teaser]);

  // The embedding page (embed.js) also needs to know which side to anchor the
  // iframe on -- that's a fact about the saved config, not something embed.js
  // can know on its own, so we hand it over the same way we hand over size.
  useEffect(() => {
    if (typeof window === "undefined" || window.parent === window) return;
    window.parent.postMessage({ source: "ai-employee-widget", type: "position", position }, "*");
  }, [position]);

  const dismissTeaser = () => {
    setTeaser(null);
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem(teaserKey, "1");
  };

  const openFromTeaser = () => {
    dismissTeaser();
    setOpen(true);
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setLoading(true);
    try {
      const { data } = await api.post("/chat", { business_id: businessId, message: text, conversation_id: convId, visitor_id: visitorId });
      if (data.error === "limit_reached") {
        setMessages((m) => [...m, { role: "assistant", text: data.message }]);
      } else {
        setConvId(data.conversation_id);
        setVisitorId(data.visitor_id);
        localStorage.setItem(`vis_${businessId}`, data.visitor_id);
        setMessages((m) => [...m, { role: "assistant", text: data.answer, unanswered: data.unanswered }]);
      }
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Something went wrong. Try again in a moment." }]);
    }
    setLoading(false);
  };

  const submitHandoff = async () => {
    if (!convId) return;
    try {
      await api.post("/chat/handoff", {
        business_id: businessId,
        conversation_id: convId,
        visitor_email: handoffForm?.email || null,
        visitor_name: handoffForm?.name || null,
        note: handoffForm?.note || null,
      });
      setHandoff(true);
      setHandoffForm(null);
      setMessages((m) => [...m, { role: "assistant", text: "Thanks -- I've passed this along to the team. Someone will reach out shortly." }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Hmm, couldn't reach the team just now -- please try again." }]);
    }
  };

  const entranceClass = reducedMotion ? "" : `transition-all duration-500 ease-out ${mounted ? "opacity-100 scale-100 translate-y-0" : "opacity-0 scale-75 translate-y-4"}`;
  // The idle "breathe" glow and gentle float are cosmetic flourishes only -- both
  // are no-ops (classes simply omitted) under prefers-reduced-motion, and neither
  // ever plays once the panel is open (a pulsing button behind an open panel would
  // just be a distraction, not a feature).
  const showIdleFx = !open && !reducedMotion && everOpened === false;

  return (
    <div className="fixed inset-0 pointer-events-none">
      {!reducedMotion && (
        <style>{`
          @keyframes ai-emp-pulse-ring { 0% { box-shadow: 0 0 0 0 ${primary}55; } 70% { box-shadow: 0 0 0 14px ${primary}00; } 100% { box-shadow: 0 0 0 0 ${primary}00; } }
          @keyframes ai-emp-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
          .ai-emp-pulse { animation: ai-emp-pulse-ring 2.6s cubic-bezier(0.4,0,0.6,1) infinite; }
          .ai-emp-float { animation: ai-emp-float 3.2s ease-in-out infinite; }
        `}</style>
      )}
      <div className={`absolute bottom-4 ${cornerClasses} pointer-events-auto flex flex-col gap-3`}>
        {!open && teaser && (
          <div
            className={`max-w-[240px] rounded-2xl ${teaserTailClass} shadow-lg border bg-white px-3.5 py-2.5 text-sm text-gray-800 relative ${reducedMotion ? "" : "animate-in fade-in slide-in-from-bottom-2"}`}
            style={{ borderColor: "rgba(0,0,0,0.08)" }}
            data-testid="widget-teaser"
            role="status"
          >
            <button
              onClick={dismissTeaser}
              aria-label="Dismiss"
              className={`absolute -top-2 ${teaserCloseClass} w-5 h-5 rounded-full bg-gray-200 hover:bg-gray-300 flex items-center justify-center text-gray-600 transition-colors`}
            >
              <X size={11} weight="bold" />
            </button>
            <button onClick={openFromTeaser} className="text-left w-full">
              {teaser}
            </button>
          </div>
        )}

        {open && (
          <div
            className={`w-[360px] max-w-[calc(100vw-2rem)] h-[560px] max-h-[calc(100vh-6rem)] rounded-lg shadow-xl border overflow-hidden flex flex-col bg-white ${reducedMotion ? "" : "animate-in fade-in slide-in-from-bottom-4 duration-300"}`}
            style={{ borderColor: "rgba(0,0,0,0.08)" }}
            data-testid="chat-window"
            role="dialog"
            aria-modal="true"
            aria-label={`Chat with ${businessName}`}
          >
            <div style={{ background: primary }} className="text-white px-4 py-3 flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.2em]" style={{ color: accent }}>AI Employee</div>
                <div className="font-display text-base">{businessName}</div>
              </div>
              <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white transition-colors" aria-label="Close chat" data-testid="close-widget"><X size={20} /></button>
            </div>
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#F7F7F5]" aria-live="polite">
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] px-3 py-2 rounded-lg text-sm whitespace-pre-line ${m.role === "user" ? "text-white" : "bg-white text-gray-900 border border-gray-200"}`}
                    style={m.role === "user" ? { background: primary } : {}}
                  >
                    {m.text}
                    {m.unanswered && !handoff && (
                      <div className="mt-2 pt-2 border-t border-gray-200">
                        <button onClick={() => setHandoffForm({ email: "", name: "", note: "" })} className="text-xs underline" style={{ color: primary }} data-testid="handoff-btn">
                          Connect me with a human
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex items-center gap-1 pl-1" aria-label="AI is typing">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className={`w-1.5 h-1.5 rounded-full bg-gray-400 ${reducedMotion ? "" : "animate-bounce"}`} style={reducedMotion ? {} : { animationDelay: `${i * 0.12}s` }} />
                  ))}
                </div>
              )}

              {handoffForm && (
                <div className="bg-white border border-gray-200 rounded-lg p-3 space-y-2" data-testid="handoff-form">
                  <div className="text-xs font-medium text-gray-700">What's going on, and how should we reach you?</div>
                  <textarea
                    value={handoffForm.note}
                    onChange={(e) => setHandoffForm((f) => ({ ...f, note: e.target.value }))}
                    placeholder="Briefly describe what you need help with…"
                    rows={2}
                    aria-label="What you need help with"
                    className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-200 outline-none focus:border-gray-400 resize-none"
                  />
                  <input
                    value={handoffForm.name}
                    onChange={(e) => setHandoffForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Your name"
                    aria-label="Your name"
                    className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-200 outline-none focus:border-gray-400"
                  />
                  <input
                    value={handoffForm.email}
                    onChange={(e) => setHandoffForm((f) => ({ ...f, email: e.target.value }))}
                    placeholder="Your email (so we can reply)"
                    type="email"
                    aria-label="Your email"
                    className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-200 outline-none focus:border-gray-400"
                  />
                  <div className="flex items-center gap-2 justify-end">
                    <button onClick={() => setHandoffForm(null)} className="text-xs text-gray-500 hover:text-gray-800 px-2 py-1">Cancel</button>
                    <button
                      onClick={submitHandoff}
                      style={{ background: primary }}
                      className="text-xs text-white px-3 py-1.5 rounded-md flex items-center gap-1 hover:opacity-90 transition-opacity"
                      data-testid="handoff-submit"
                    >
                      <PaperPlaneTilt size={12} weight="fill" /> Send to the team
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="border-t border-gray-200 p-3 bg-white">
              <div className="flex items-center gap-2">
                <input
                  ref={inputRef}
                  data-testid="widget-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder="Ask anything about us…"
                  aria-label="Type your message"
                  className="flex-1 text-sm px-3 py-2 rounded-md border border-gray-200 outline-none focus:border-gray-400"
                />
                <button
                  data-testid="widget-send"
                  onClick={send}
                  aria-label="Send message"
                  className="p-2 rounded-md text-white transition-transform hover:scale-105"
                  style={{ background: primary }}
                >
                  <PaperPlaneRight size={16} weight="fill" />
                </button>
              </div>
              {!handoff && !handoffForm && (
                <button onClick={() => setHandoffForm({ email: "", name: "", note: "" })} className="mt-2 text-[11px] text-gray-500 hover:text-gray-800 flex items-center gap-1 transition-colors" data-testid="footer-handoff">
                  <User size={12} /> Talk to a human
                </button>
              )}
              {showBranding && (
                <div className="text-[10px] text-gray-400 mt-2 text-center">Powered by AI Employee</div>
              )}
            </div>
          </div>
        )}
        <button
          ref={toggleRef}
          data-testid="widget-toggle"
          onClick={() => { dismissTeaser(); setOpen(!open); }}
          aria-label={open ? "Close chat" : `Chat with ${businessName}`}
          aria-expanded={open}
          style={{ background: primary }}
          className={`w-14 h-14 rounded-full shadow-lg text-white flex items-center justify-center transition-all duration-300 hover:scale-110 hover:shadow-xl active:scale-95 ${entranceClass} ${showIdleFx && pulseEnabled ? "ai-emp-pulse" : ""} ${showIdleFx ? "ai-emp-float" : ""}`}
        >
          {open ? <X size={22} weight="bold" /> : <ChatCircleDots size={24} weight="fill" />}
        </button>
      </div>
    </div>
  );
}

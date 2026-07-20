import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Marquee from "react-fast-marquee";
import { ArrowUpRight, Sparkle, ShieldCheck, LightbulbFilament, Storefront, ChatCircleText, Buildings } from "@phosphor-icons/react";

const HERO_IMG = "https://images.unsplash.com/photo-1759038085950-1234ca8f5fed?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzV8MHwxfHNlYXJjaHwyfHxtb2Rlcm4lMjByZWNlcHRpb25pc3QlMjBkZXNrfGVufDB8fHx8MTc4NDI4MjUzNnww&ixlib=rb-4.1.0&q=85";

const testimonials = [
  { name: "Ananya Rao", role: "Coffee Shop Owner, Bengaluru", quote: "It answers 80% of our Instagram DMs instantly. Feels like a real employee, not a chatbot.",
    img: "https://images.unsplash.com/photo-1753351052363-53ce102830eb?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1ODR8MHwxfHNlYXJjaHwzfHxidXNpbmVzcyUyMG93bmVyJTIwcG9ydHJhaXR8ZW58MHx8fHwxNzg0MjgyNTM2fDA&ixlib=rb-4.1.0&q=85" },
  { name: "Meera Iyer", role: "Restaurant, Mumbai", quote: "Bookings, menu, allergens — customers get real answers 24/7. It's like hiring three people for a fraction.",
    img: "https://images.unsplash.com/photo-1717251816735-62bd01da1757?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1ODR8MHwxfHNlYXJjaHw0fHxidXNpbmVzcyUyMG93bmVyJTIwcG9ydHJhaXR8ZW58MHx8fHwxNzg0MjgyNTM2fDA&ixlib=rb-4.1.0&q=85" },
];

export default function Landing() {
  const [params] = useSearchParams();
  const ref = params.get("ref");
  React.useEffect(() => { if (ref) localStorage.setItem("pending_referral", ref); }, [ref]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-background/70 border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-2xl tracking-tight">AI Employee</span>
            <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">The intelligent front desk</span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm">
            <a href="#features" className="hover:text-primary">Product</a>
            <a href="#pricing" className="hover:text-primary">Pricing</a>
            <a href="#how" className="hover:text-primary">How it works</a>
            <Link to="/login" data-testid="nav-signin" className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 transition-opacity">Sign in</Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 py-20 md:py-28 grid md:grid-cols-12 gap-10 items-center">
          <div className="md:col-span-7">
            <div className="text-xs uppercase tracking-[0.3em] text-accent mb-6">Not another chatbot.</div>
            <h1 className="font-display text-5xl md:text-6xl font-black leading-[0.95] tracking-tight">
              Hire an <span className="italic font-light">AI Employee</span><br/>for your business.
            </h1>
            <p className="mt-6 text-lg text-muted-foreground max-w-xl leading-relaxed">
              A real front-desk assistant that answers your customers <span className="text-foreground font-medium">and</span> takes commands from you. Update hours, pricing, or widget colors — in plain English. Doctors. Restaurants. Salons. Shops. All welcome.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/login" data-testid="hero-cta" className="group inline-flex items-center gap-2 px-6 py-3 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
                Hire your AI Employee <ArrowUpRight size={18} className="group-hover:translate-x-0.5 transition-transform" />
              </Link>
              <a href="#pricing" className="px-6 py-3 rounded-md border border-border hover:bg-secondary transition-colors">See pricing</a>
            </div>
            <div className="mt-10 flex items-center gap-6 text-xs text-muted-foreground">
              <div className="flex items-center gap-2"><ShieldCheck size={14} /> Multi-tenant secure</div>
              <div className="flex items-center gap-2"><Sparkle size={14} /> Grounded in your knowledge</div>
              <div className="flex items-center gap-2"><LightbulbFilament size={14} /> Learns unanswered questions</div>
            </div>
          </div>
          <div className="md:col-span-5 relative">
            <div className="relative rounded-lg overflow-hidden border border-border">
              <img src={HERO_IMG} alt="Reception desk" className="w-full h-[420px] object-cover" />
              <div className="absolute inset-0 bg-primary/40 mix-blend-multiply" />
              <div className="absolute bottom-4 left-4 right-4 bg-white/90 backdrop-blur-md rounded-md p-4 border border-white/60">
                <div className="text-[10px] uppercase tracking-[0.2em] text-primary">Customer chat · live</div>
                <div className="text-sm mt-1 text-gray-900">"Do you have gluten-free options for dinner tonight?"</div>
                <div className="mt-2 text-sm text-primary font-medium">"Yes — our chef prepared 3 GF mains this week. Reserve at 7:30 pm?"</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Marquee */}
      <section className="border-y border-border py-6 bg-secondary/40">
        <Marquee gradient={false} speed={40} className="marquee-fade">
          {["DOCTORS · CLINICS", "RESTAURANTS · CAFES", "GYMS · STUDIOS", "SALONS · SPAS", "LAWYERS · CA", "SCHOOLS · TUTORS", "ECOMMERCE STORES", "LOCAL SHOPS", "HOTELS · BNBS"].map((t, i) => (
            <span key={i} className="mx-10 text-sm tracking-[0.3em] text-muted-foreground">{t}</span>
          ))}
        </Marquee>
      </section>

      {/* Dual mode */}
      <section className="max-w-7xl mx-auto px-6 py-24 border-b border-border">
        <div className="text-xs uppercase tracking-[0.3em] text-accent mb-4">Two employees in one</div>
        <h2 className="font-display text-4xl md:text-5xl tracking-tight max-w-3xl">Answers your customers.<br/><span className="italic font-light">Runs your business.</span></h2>
        <div className="mt-14 grid md:grid-cols-2 gap-6">
          <div className="bg-card border border-border rounded-lg p-8 relative overflow-hidden">
            <div className="text-[10px] uppercase tracking-[0.25em] text-accent mb-4">Customer-facing widget · read-only</div>
            <div className="font-display text-2xl tracking-tight">Grounded, honest, always on</div>
            <p className="mt-3 text-muted-foreground">Only speaks from your knowledge base. Says "I don't know" instead of inventing. Offers human handoff when unsure.</p>
            <div className="mt-6 space-y-2">
              <div className="bg-secondary rounded-md px-3 py-2 text-sm max-w-[85%]">"Do you deliver to Koramangala?"</div>
              <div className="bg-primary text-primary-foreground rounded-md px-3 py-2 text-sm ml-8">"Yes — free delivery on orders above ₹500 within 5km. ETA 30 mins."</div>
            </div>
          </div>
          <div className="bg-primary text-primary-foreground rounded-lg p-8 relative overflow-hidden">
            <div className="text-[10px] uppercase tracking-[0.25em] text-accent mb-4">Owner console · read + write</div>
            <div className="font-display text-2xl tracking-tight">Just tell it what to change</div>
            <p className="mt-3 opacity-80">Update hours, add pricing, change widget colors, teach new answers — in plain English. No settings pages to hunt through.</p>
            <div className="mt-6 space-y-2">
              <div className="bg-primary-foreground/10 rounded-md px-3 py-2 text-sm max-w-[85%]">"Change my closing time to 11pm and teach the AI our new refund policy: 14-day full refund."</div>
              <div className="bg-accent text-accent-foreground rounded-md px-3 py-2 text-sm ml-8">"Done. Business hours updated. New knowledge indexed. ✓"</div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="max-w-7xl mx-auto px-6 py-24">
        <div className="text-xs uppercase tracking-[0.3em] text-accent mb-4">What makes it different</div>
        <h2 className="font-display text-4xl md:text-5xl tracking-tight max-w-2xl">A front desk that knows your business — not the internet.</h2>
        <div className="mt-14 grid md:grid-cols-12 gap-4">
          {[
            { c: "md:col-span-7", title: "Website → Knowledge in 30 seconds", body: "Paste your URL. We crawl, structure, and turn your site into a searchable knowledge base. No forms, no consultants.", Icon: Storefront },
            { c: "md:col-span-5", title: "One-line snippet", body: "Copy a single <script> tag. Paste it in your site. Done — like Intercom, but grounded in your data.", Icon: ChatCircleText },
            { c: "md:col-span-5", title: "Answers, never invention", body: "Retrieval-augmented. If the answer isn't in your knowledge, it says so and offers a human handoff.", Icon: ShieldCheck },
            { c: "md:col-span-7", title: "Ask your business anything", body: '"Summarize today\'s chats." "What couldn\'t we answer?" "Generate FAQs." Your dashboard is a conversation.', Icon: LightbulbFilament },
            { c: "md:col-span-12", title: "Improves every week", body: "Every unanswered question becomes a training moment. Answer once, and the AI never fails at it again.", Icon: Sparkle },
          ].map((f, i) => (
            <div key={i} className={`${f.c} bg-card border border-border rounded-lg p-8 relative overflow-hidden group hover:-translate-y-1 transition-transform duration-200`}>
              <f.Icon size={26} weight="duotone" className="text-accent mb-6" />
              <div className="font-display text-2xl tracking-tight">{f.title}</div>
              <p className="mt-3 text-muted-foreground leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How */}
      <section id="how" className="bg-secondary/40 border-y border-border py-24">
        <div className="max-w-7xl mx-auto px-6">
          <h2 className="font-display text-4xl md:text-5xl tracking-tight">Three steps.<br/>No dev team required.</h2>
          <div className="mt-12 grid md:grid-cols-3 gap-6">
            {[
              { n: "01", t: "Sign up with Google", d: "Create your first business. Enter only what matters." },
              { n: "02", t: "Paste your URL", d: "We crawl and build your knowledge base. Upload PDFs to top it up." },
              { n: "03", t: "Copy the snippet", d: "Paste one line on your site. Your AI Employee starts working." },
            ].map((s, i) => (
              <div key={i} className="bg-card border border-border rounded-lg p-8">
                <div className="text-xs tracking-[0.3em] text-accent">{s.n}</div>
                <div className="font-display text-2xl mt-3">{s.t}</div>
                <p className="mt-2 text-muted-foreground">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="max-w-7xl mx-auto px-6 py-24 grid md:grid-cols-2 gap-8">
        {testimonials.map((t) => (
          <div key={t.name} className="bg-card border border-border rounded-lg p-6 flex gap-5">
            <img src={t.img} alt={t.name} className="w-20 h-20 object-cover rounded-md flex-shrink-0" />
            <div>
              <p className="text-lg font-display leading-snug">"{t.quote}"</p>
              <div className="mt-3 text-sm"><span className="font-medium">{t.name}</span> · <span className="text-muted-foreground">{t.role}</span></div>
            </div>
          </div>
        ))}
      </section>

      {/* Pricing */}
      <section id="pricing" className="bg-primary text-primary-foreground py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-xs uppercase tracking-[0.3em] text-accent mb-4">Pricing</div>
          <h2 className="font-display text-4xl md:text-5xl">Start free. Upgrade when it earns its keep.</h2>
          <div className="mt-14 grid md:grid-cols-3 gap-6">
            {[
              { k: "free", n: "Free", p: 0, feat: ["100 chats / month", "AI Employee branding", "1 business"] },
              { k: "starter", n: "Starter", p: 999, feat: ["2,000 chats / month", "No branding", "Widget customization", "Email support"], hi: true },
              { k: "pro", n: "Pro", p: 2999, feat: ["10,000 chats / month", "Advanced analytics", "Priority support", "Unlimited uploads"] },
            ].map((p) => (
              <div key={p.k} className={`rounded-lg p-8 ${p.hi ? "bg-accent text-accent-foreground border-2 border-accent" : "bg-primary-foreground/5 border border-primary-foreground/20"}`}>
                <div className="font-display text-2xl">{p.n}</div>
                <div className="mt-4 font-display text-5xl">₹{p.p}<span className="text-base font-normal opacity-70">/mo</span></div>
                <ul className="mt-6 space-y-2 text-sm">
                  {p.feat.map((f) => <li key={f} className="flex gap-2"><span className="text-accent">•</span> {f}</li>)}
                </ul>
                <Link to="/login" data-testid={`pricing-cta-${p.k}`} className={`mt-6 block text-center py-3 rounded-md transition-colors ${p.hi ? "bg-primary text-primary-foreground hover:opacity-90" : "bg-primary-foreground text-primary hover:bg-accent hover:text-accent-foreground"}`}>Get started</Link>
              </div>
            ))}
          </div>
          <p className="mt-8 text-sm opacity-70">Refer a business → get 25% off for 12 months when they subscribe.</p>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-7xl mx-auto px-6 py-24 text-center">
        <h2 className="font-display text-5xl md:text-6xl tracking-tight max-w-3xl mx-auto">Give your business a second brain.</h2>
        <Link to="/login" data-testid="footer-cta" className="mt-8 inline-flex items-center gap-2 px-8 py-4 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
          Hire your AI Employee <ArrowUpRight size={18} />
        </Link>
      </section>

      <footer className="border-t border-border py-8 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} AI Employee. Not a chatbot.
      </footer>
    </div>
  );
}

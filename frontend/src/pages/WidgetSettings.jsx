import React, { useEffect, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Copy, QrCode, EnvelopeSimple, Link as LinkIcon } from "@phosphor-icons/react";
import ChatWidget from "../components/ChatWidget";

const GUIDES = [
  { id: "wordpress", name: "WordPress",
    steps: [
      "In your WordPress admin, go to Appearance → Theme File Editor (or install the free 'Insert Headers and Footers' plugin).",
      "Open the file 'footer.php' (or open the plugin and find the 'Scripts in Footer' box).",
      "Paste the snippet just before </body>.",
      "Click 'Update File' or 'Save'. Refresh your website — the chat bubble appears in the bottom-right."
    ]},
  { id: "shopify", name: "Shopify",
    steps: [
      "In Shopify admin: Online Store → Themes → click 'Actions' → 'Edit code'.",
      "Under 'Layout', open 'theme.liquid'.",
      "Scroll to the bottom and paste the snippet just before </body>.",
      "Click 'Save'. Your storefront now shows the AI Employee bubble."
    ]},
  { id: "wix", name: "Wix",
    steps: [
      "Wix dashboard → Settings → Custom Code (under Advanced).",
      "Click '+ Add Custom Code'.",
      "Paste the snippet in the code box, name it 'AI Employee', choose 'Body — end'.",
      "Apply to 'All pages' and click 'Apply'."
    ]},
  { id: "squarespace", name: "Squarespace",
    steps: [
      "In your Squarespace admin: Settings → Advanced → Code Injection.",
      "Paste the snippet in the 'Footer' box.",
      "Click 'Save'. Refresh your live site to see the bubble."
    ]},
  { id: "godaddy", name: "GoDaddy / Website Builder",
    steps: [
      "Open your GoDaddy Website Builder → 'Edit Website'.",
      "Add a new 'HTML' section at the bottom of any page (or in the footer).",
      "Paste the snippet and click 'Done'. Publish your site."
    ]},
  { id: "webflow", name: "Webflow",
    steps: [
      "Webflow Designer → Project Settings → Custom Code.",
      "Paste the snippet in the 'Footer Code' box.",
      "Save and Publish your site."
    ]},
];

export default function WidgetSettings() {
  const { current, refresh } = useBiz();
  const [w, setW] = useState(null);
  const [snippet, setSnippet] = useState("");
  const [tab, setTab] = useState("install"); // install | design
  const [guide, setGuide] = useState("wordpress");

  useEffect(() => {
    if (!current) return;
    setW({ ...current.widget });
    setSnippet(`<script async src="${window.location.origin}/embed.js" data-business="${current.business_id}"></script>`);
  }, [current]);

  const save = async () => {
    try {
      await api.patch(`/businesses/${current.business_id}`, { widget: w });
      await refresh();
      toast.success("Widget updated");
    } catch { toast.error("Save failed"); }
  };

  const copy = (text, label) => { navigator.clipboard.writeText(text); toast.success(`${label} copied`); };

  if (!current || !w) return null;

  const talkUrl = `${window.location.origin}/talk/${current.business_id}`;
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(talkUrl)}&bgcolor=F7F7F5`;

  const emailBody = encodeURIComponent(
`Hi,

Please add this one line to our website — just before </body> on every page:

${snippet}

It installs our new AI Employee (the chat bubble in the bottom-right corner that answers customer questions 24/7).

If you use WordPress, Shopify, Wix, Squarespace, or a website builder — a plugin/settings option usually exists to paste this. Please let me know once it's live.

Thanks!`);
  const mailto = `mailto:?subject=${encodeURIComponent("Please install our AI Employee")}&body=${emailBody}`;

  return (
    <div className="p-8 space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Widget</div>
        <h1 className="font-display text-4xl tracking-tight">Install & customize.</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border">
        {[["install","Install (3 ways)"],["design","Design"]].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`ws-tab-${k}`}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${tab===k ? "border-accent text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>{l}</button>
        ))}
      </div>

      {tab === "install" && (
        <div className="space-y-6">
          {/* 3 install methods */}
          <div className="grid md:grid-cols-3 gap-4">
            {/* Method 1: Share a link */}
            <div className="bg-card border border-border rounded-lg p-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent mb-2">Option 1 · Easiest</div>
              <div className="font-display text-xl">No website? Share a link.</div>
              <p className="text-sm text-muted-foreground mt-2">Get a hosted chat page. Share on Instagram bio, WhatsApp, print a QR on your business card.</p>
              <div className="mt-4 bg-secondary rounded-md p-3 text-xs font-mono break-all">{talkUrl}</div>
              <div className="mt-3 flex gap-2">
                <button onClick={() => copy(talkUrl, "Link")} data-testid="copy-talk-link" className="text-xs px-3 py-2 rounded-md border border-border hover:bg-secondary flex items-center gap-2"><LinkIcon size={14} /> Copy link</button>
                <a href={talkUrl} target="_blank" rel="noreferrer" className="text-xs px-3 py-2 rounded-md border border-border hover:bg-secondary flex items-center gap-2">Open ↗</a>
              </div>
              <details className="mt-4">
                <summary className="text-xs text-accent cursor-pointer flex items-center gap-1"><QrCode size={14} /> Show QR code</summary>
                <img src={qrUrl} alt="QR" className="mt-3 rounded-md border border-border" />
              </details>
            </div>

            {/* Method 2: Email developer */}
            <div className="bg-card border border-border rounded-lg p-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent mb-2">Option 2 · Have a developer?</div>
              <div className="font-display text-xl">Email them the snippet.</div>
              <p className="text-sm text-muted-foreground mt-2">Pre-written email with everything they need. Takes them under 2 minutes to install.</p>
              <a href={mailto} data-testid="email-dev" className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors text-sm">
                <EnvelopeSimple size={14} /> Email my developer
              </a>
              <div className="mt-3 text-[11px] text-muted-foreground">Opens your email app with a ready-to-send message.</div>
            </div>

            {/* Method 3: DIY */}
            <div className="bg-card border border-border rounded-lg p-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent mb-2">Option 3 · Do it yourself</div>
              <div className="font-display text-xl">Pick your platform.</div>
              <p className="text-sm text-muted-foreground mt-2">Step-by-step guide for WordPress, Shopify, Wix, Squarespace and more.</p>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {GUIDES.map((g) => (
                  <button key={g.id} onClick={() => setGuide(g.id)} data-testid={`guide-${g.id}`}
                    className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${guide===g.id ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-secondary"}`}>
                    {g.name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Snippet + selected guide */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-card border border-border rounded-lg p-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-3">Your snippet</div>
              <div className="bg-secondary rounded-md p-4 text-xs font-mono break-all">{snippet}</div>
              <button onClick={() => copy(snippet, "Snippet")} data-testid="copy-snippet" className="mt-3 px-4 py-2 rounded-md border border-border hover:bg-secondary transition-colors text-sm flex items-center gap-2"><Copy size={14} /> Copy snippet</button>
              <p className="mt-3 text-xs text-muted-foreground">This one line adds the chat bubble to every page. Paste it once, works everywhere.</p>
            </div>
            <div className="bg-card border border-border rounded-lg p-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent mb-3">{GUIDES.find((g) => g.id === guide)?.name} — step by step</div>
              <ol className="space-y-3 text-sm">
                {GUIDES.find((g) => g.id === guide)?.steps.map((s, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="w-5 h-5 rounded-full bg-accent text-accent-foreground text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{i+1}</span>
                    <span className="text-foreground/90 leading-relaxed">{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      )}

      {tab === "design" && (
        <>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-card border border-border rounded-lg p-6 space-y-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Primary color</div>
                <input type="color" value={w.primary_color} onChange={(e) => setW({ ...w, primary_color: e.target.value })} data-testid="widget-primary" className="h-10 w-20 rounded border border-border" />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Accent color</div>
                <input type="color" value={w.accent_color} onChange={(e) => setW({ ...w, accent_color: e.target.value })} data-testid="widget-accent" className="h-10 w-20 rounded border border-border" />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Welcome message</div>
                <textarea value={w.welcome_message} onChange={(e) => setW({ ...w, welcome_message: e.target.value })} data-testid="widget-welcome" rows={3} className="w-full px-3 py-2 rounded-md border border-border bg-background" />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-2">Position</div>
                <select value={w.position} onChange={(e) => setW({ ...w, position: e.target.value })} data-testid="widget-position" className="px-3 py-2 rounded-md border border-border bg-background">
                  <option value="bottom-right">Bottom right</option>
                  <option value="bottom-left">Bottom left</option>
                </select>
              </div>
              <label className={`flex items-center gap-2 text-sm ${current.plan === "free" ? "opacity-60" : ""}`}>
                <input
                  type="checkbox"
                  checked={current.plan === "free" ? true : w.show_branding}
                  disabled={current.plan === "free"}
                  onChange={(e) => setW({ ...w, show_branding: e.target.checked })}
                  data-testid="widget-branding"
                />
                Show "Powered by AI Employee" {current.plan === "free" ? "(required on Free plan -- upgrade to remove)" : ""}
              </label>
              <button onClick={save} data-testid="widget-save" className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground transition-colors">Save changes</button>
            </div>

            <div className="relative bg-secondary rounded-lg h-[520px] overflow-hidden border border-border">
              <div className="absolute top-3 left-3 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Live preview</div>
              <ChatWidget businessId={current.business_id} config={{ business_name: current.name, widget: w }} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

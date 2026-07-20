import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card } from "./_ui";

const LABELS = {
  referrals_enabled: "Referrals program",
  widget_customization: "Widget customization",
  file_uploads: "File uploads",
  website_crawler: "Website crawler",
  owner_write_actions: "Owner write actions (AI commands)",
  human_handoff: "Human handoff button",
};

export default function FeatureFlags() {
  const [flags, setFlags] = useState({});
  useEffect(() => { api.get("/admin/flags").then(({ data }) => setFlags(data)); }, []);
  const toggle = async (k) => {
    const next = !flags[k];
    setFlags({ ...flags, [k]: next });
    try { await api.post("/admin/flags", { key: k, value: next }); toast.success(`${LABELS[k]} → ${next ? "ON" : "OFF"}`); }
    catch { toast.error("Failed"); setFlags((f) => ({ ...f, [k]: !next })); }
  };
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Rollouts" title="Feature Flags" />
      <Card>
        <div className="divide-y divide-border">
          {Object.keys(LABELS).map((k) => (
            <div key={k} className="p-4 flex items-center justify-between">
              <div>
                <div className="font-medium">{LABELS[k]}</div>
                <div className="text-xs text-muted-foreground font-mono">{k}</div>
              </div>
              <button onClick={() => toggle(k)} data-testid={`flag-${k}`}
                className={`relative w-12 h-6 rounded-full transition-colors ${flags[k] ? "bg-accent" : "bg-secondary"}`}>
                <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${flags[k] ? "translate-x-6" : "translate-x-0.5"}`} />
              </button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

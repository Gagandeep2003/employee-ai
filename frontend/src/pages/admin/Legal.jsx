import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Btn, Pill } from "./_ui";
import { CheckCircle, Clock } from "@phosphor-icons/react";

export default function AdminLegal() {
  const [types, setTypes] = useState(null);
  const [active, setActive] = useState(null);
  const [versions, setVersions] = useState([]);
  const [draft, setDraft] = useState({ title: "", content: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/legal/document-types").then(({ data }) => {
      setTypes(data.types);
      setActive(Object.keys(data.types)[0]);
    });
  }, []);

  const load = (docType) => {
    setActive(docType);
    api.get(`/legal/admin/${docType}/versions`).then(({ data }) => {
      setVersions(data);
      const latest = data[0];
      if (latest) {
        api.get(`/legal/admin/${docType}/versions/${latest.version}`).then(({ data: full }) => {
          setDraft({ title: full.title, content: full.content });
        });
      } else {
        setDraft({ title: types[docType], content: "" });
      }
    });
  };
  useEffect(() => { if (types && active) load(active); }, [types]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveDraft = async () => {
    if (!draft.title.trim() || !draft.content.trim()) { toast.error("Title and content are required"); return; }
    setSaving(true);
    try {
      await api.post(`/legal/admin/${active}/draft`, draft);
      toast.success("Draft saved -- not live until you publish it");
      load(active);
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    setSaving(false);
  };

  const publish = async (version) => {
    if (!window.confirm(`Publish version ${version}? This becomes the live, public document immediately.`)) return;
    try {
      await api.post(`/legal/admin/${active}/versions/${version}/publish`);
      toast.success("Published");
      load(active);
    } catch { toast.error("Publish failed"); }
  };

  const viewVersion = async (version) => {
    const { data } = await api.get(`/legal/admin/${active}/versions/${version}`);
    setDraft({ title: data.title, content: data.content });
  };

  if (!types) return null;

  return (
    <div>
      <H1 eyebrow="Compliance" title="Legal documents" />
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-3 space-y-1">
          {Object.entries(types).map(([key, label]) => (
            <button key={key} onClick={() => load(key)} data-testid={`legal-type-${key}`}
              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${active === key ? "bg-primary text-primary-foreground" : "hover:bg-secondary"}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="col-span-9 space-y-6">
          <Card title={`Edit — ${types[active]}`}>
            <div className="p-4 space-y-3">
              <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                data-testid="legal-title" placeholder="Document title"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm" />
              <textarea value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })}
                data-testid="legal-content" rows={16} placeholder="Markdown content…"
                className="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono" />
              <div className="flex items-center gap-2">
                <Btn onClick={saveDraft} disabled={saving} testid="legal-save-draft">Save as new draft</Btn>
                <span className="text-xs text-muted-foreground">Saving creates a new version -- it won't go live until published below.</span>
              </div>
            </div>
          </Card>

          <Card title="Version history">
            <div className="divide-y divide-border">
              {versions.map((v) => (
                <div key={v.version} className="p-4 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium">v{v.version}</span>
                    {v.is_published ? (
                      <Pill tone="ok"><CheckCircle size={11} weight="fill" className="inline mr-1" /> Live</Pill>
                    ) : (
                      <Pill><Clock size={11} className="inline mr-1" /> Draft</Pill>
                    )}
                    <span className="text-xs text-muted-foreground">{new Date(v.created_at).toLocaleString()}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => viewVersion(v.version)} className="text-xs text-muted-foreground hover:text-foreground">View</button>
                    {!v.is_published && <Btn variant="accent" onClick={() => publish(v.version)} testid={`publish-v${v.version}`}>Publish</Btn>}
                  </div>
                </div>
              ))}
              {!versions.length && <div className="p-6 text-sm text-muted-foreground text-center">No versions yet -- save a draft above to create the first one.</div>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

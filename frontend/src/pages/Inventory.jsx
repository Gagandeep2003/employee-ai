import React, { useEffect, useRef, useState } from "react";
import { useBiz } from "../components/AppShell";
import { api } from "../lib/api";
import { toast } from "sonner";
import { UploadSimple, Trash, Package } from "@phosphor-icons/react";

export default function Inventory() {
  const { current } = useBiz();
  const [items, setItems] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const refresh = () => {
    if (!current) return;
    api.get(`/businesses/${current.business_id}/inventory`).then(({ data }) => setItems(data));
  };
  useEffect(refresh, [current]);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post(`/businesses/${current.business_id}/inventory/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Loaded ${data.items_loaded} products -- your AI knows them now`);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed -- check your CSV has a name column");
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const clearAll = async () => {
    if (!window.confirm("Remove all inventory items? This can't be undone -- you'd need to re-upload the CSV.")) return;
    try {
      await api.delete(`/businesses/${current.business_id}/inventory`);
      toast.success("Inventory cleared");
      refresh();
    } catch { toast.error("Failed to clear"); }
  };

  if (!current) return null;

  return (
    <div className="p-8 space-y-6 max-w-4xl">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Inventory</div>
        <h1 className="font-display text-4xl tracking-tight">Keep stock &amp; pricing current.</h1>
        <p className="text-sm text-muted-foreground mt-2">
          Upload a CSV of your products and your AI can answer "do you have X in stock" or "how much is Y"
          accurately. Re-uploading replaces the whole list -- that's the entire update workflow, no editing
          needed. Needs a <span className="font-mono text-xs">name</span> column at minimum; <span className="font-mono text-xs">price</span>,
          <span className="font-mono text-xs"> stock</span>, and <span className="font-mono text-xs">description</span> columns are picked up automatically if present.
        </p>
      </div>

      <div className="bg-card border border-border rounded-lg p-6 flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="font-medium">{items.length} product{items.length === 1 ? "" : "s"} loaded</div>
          <div className="text-xs text-muted-foreground">
            {items[0]?.created_at ? `Last uploaded ${new Date(items[0].created_at).toLocaleDateString()}` : "Nothing uploaded yet"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" id="inv-csv"
            onChange={(e) => upload(e.target.files?.[0])} data-testid="inventory-file-input" />
          <label htmlFor="inv-csv" data-testid="inventory-upload-btn"
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm flex items-center gap-2 cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors">
            <UploadSimple size={14} /> {uploading ? "Uploading…" : "Upload CSV"}
          </label>
          {items.length > 0 && (
            <button onClick={clearAll} data-testid="inventory-clear-btn" className="px-3 py-2 rounded-md border border-border text-sm text-muted-foreground hover:text-destructive hover:border-destructive/50">
              <Trash size={14} />
            </button>
          )}
        </div>
      </div>

      <div className="bg-card border border-border rounded-lg">
        {items.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground flex flex-col items-center gap-2">
            <Package size={28} className="opacity-40" />
            No inventory uploaded yet -- your AI will fall back to whatever's in your knowledge base or website.
          </div>
        ) : (
          <div className="divide-y divide-border max-h-[32rem] overflow-y-auto">
            {items.map((it) => (
              <div key={it.id} className="p-3 text-sm" data-testid={`inventory-item-${it.id}`}>
                {it.text}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

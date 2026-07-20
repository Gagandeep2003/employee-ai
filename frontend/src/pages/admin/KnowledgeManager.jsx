import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { H1, Card, Row, Th, Td, Pill, fmtDT } from "./_ui";

export default function KnowledgeManager() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/admin/knowledge").then(({ data }) => setItems(data)); }, []);
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Uploads inventory" title="Knowledge Manager" />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>File</Th><Th>Business</Th><Th>Type</Th><Th>Size</Th><Th>Uploaded</Th>
            </tr></thead>
            <tbody>
              {items.map((f) => (
                <Row key={f.id}>
                  <Td>{f.original_filename}<div className="text-[11px] text-muted-foreground font-mono">{f.id}</div></Td>
                  <Td>{f.business_name}</Td>
                  <Td><Pill>{(f.content_type || "").split("/").pop()}</Pill></Td>
                  <Td className="text-xs">{Math.round((f.size || 0) / 1024)} KB</Td>
                  <Td className="text-xs text-muted-foreground">{fmtDT(f.created_at)}</Td>
                </Row>
              ))}
              {!items.length && <tr><Td className="text-center text-muted-foreground py-8" colSpan={5}>No files uploaded yet.</Td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

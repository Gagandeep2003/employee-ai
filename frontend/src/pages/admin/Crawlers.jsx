import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Row, Th, Td, Btn, Pill } from "./_ui";

export default function Crawlers() {
  const [items, setItems] = useState([]);
  const load = () => api.get("/admin/crawls").then(({ data }) => setItems(data));
  useEffect(() => { load(); const int = setInterval(load, 5000); return () => clearInterval(int); }, []);
  const recrawl = async (bid) => {
    try { await api.post(`/businesses/${bid}/recrawl`); toast.success("Re-queued"); load(); }
    catch { toast.error("Failed"); }
  };
  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Website ingestion" title="Crawler Monitor" />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Business</Th><Th>Website</Th><Th>Status</Th><Th>Progress</Th><Th>Chunks</Th><Th>KScore</Th><Th></Th>
            </tr></thead>
            <tbody>
              {items.map((b) => (
                <Row key={b.business_id}>
                  <Td>{b.name}</Td>
                  <Td className="text-xs"><a href={b.website} target="_blank" rel="noreferrer" className="text-accent hover:underline">{b.website}</a></Td>
                  <Td><Pill tone={b.crawl_status === "done" ? "ok" : b.crawl_status === "crawling" ? "warn" : b.crawl_status === "error" ? "danger" : "default"}>{b.crawl_status}</Pill></Td>
                  <Td>{b.crawl_progress}%</Td>
                  <Td>{b.chunks}</Td>
                  <Td>{b.knowledge_score}</Td>
                  <Td className="text-right"><Btn variant="ghost" onClick={() => recrawl(b.business_id)}>Retry</Btn></Td>
                </Row>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

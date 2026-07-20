import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import ChatWidget from "../components/ChatWidget";

export default function WidgetPage() {
  const { businessId } = useParams();
  const [config, setConfig] = useState(null);
  useEffect(() => {
    api.get(`/chat/business/${businessId}/widget-config`).then(({ data }) => setConfig(data)).catch(() => {});
  }, [businessId]);
  if (!config) return <div className="min-h-screen"></div>;
  return (
    <div className="min-h-screen" style={{ background: "transparent" }}>
      <ChatWidget businessId={businessId} config={config} />
    </div>
  );
}

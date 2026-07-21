import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import ChatWidget from "../components/ChatWidget";

export default function WidgetPage() {
  const { businessId } = useParams();
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get(`/chat/business/${businessId}/widget-config`)
      .then(({ data }) => { if (!cancelled) setConfig(data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [businessId]);

  if (error) {
    // Previously this silently stayed blank forever on failure (wrong/deleted
    // business id, or the backend being unreachable) -- now it says so.
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground p-6 text-center">
        This chat couldn't load. The link may be out of date -- please check with the business.
      </div>
    );
  }
  if (!config) return <div className="min-h-screen"></div>;

  return (
    <div className="min-h-screen" style={{ background: "transparent" }}>
      <ChatWidget businessId={businessId} config={config} />
    </div>
  );
}

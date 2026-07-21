import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import ChatWidget from "../components/ChatWidget";

// Mirrors ChatWidget.jsx's own reportSize() -- lets this page tell the
// embedding iframe (see public/embed.js) how much room it needs before
// ChatWidget has actually mounted (while config is loading, or if it fails
// to load at all). No-op when this page isn't inside an iframe.
function reportSize(w, h) {
  if (typeof window === "undefined" || window.parent === window) return;
  window.parent.postMessage({ source: "ai-employee-widget", type: "size", width: w, height: h }, "*");
}

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

  // This page only ever renders inside a small, widget-sized iframe --
  // standalone or embedded via public/embed.js -- never a full page layout.
  // The surrounding document can still have its own (often white) background
  // showing through around our content, so force it transparent for as long
  // as this page is mounted, and put back whatever was there on unmount.
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const prevHtmlBg = html.style.background;
    const prevBodyBg = body.style.background;
    html.style.background = "transparent";
    body.style.background = "transparent";
    return () => {
      html.style.background = prevHtmlBg;
      body.style.background = prevBodyBg;
    };
  }, []);

  // ChatWidget isn't mounted yet to report its own size, so if loading fails
  // we grow the iframe just enough to show the error message instead of it
  // being silently clipped at whatever size it happened to be.
  useEffect(() => {
    if (error) reportSize(280, 110);
  }, [error]);

  if (error) {
    // Previously this silently stayed blank forever on failure (wrong/deleted
    // business id, or the backend being unreachable) -- now it says so.
    return (
      <div className="text-sm text-muted-foreground p-3 text-center">
        This chat couldn't load. The link may be out of date -- please check with the business.
      </div>
    );
  }

  if (!config) return null;

  return <ChatWidget businessId={businessId} config={config} />;
}

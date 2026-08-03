import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";

// Minimal, dependency-free markdown-ish renderer for admin-authored legal content --
// headers, paragraphs, bullet lists, and **bold** only. Deliberately not
// dangerouslySetInnerHTML, even though this content is admin-authored, so there's no HTML
// injection surface at all, not even from a compromised admin account.
function renderBlock(text, key) {
  const boldParts = text.split(/\*\*(.+?)\*\*/g);
  const content = boldParts.map((part, i) => (i % 2 === 1 ? <strong key={i}>{part}</strong> : part));
  return <p key={key} className="leading-relaxed">{content}</p>;
}

function MarkdownLite({ content }) {
  const lines = content.split("\n");
  const blocks = [];
  let listBuffer = [];
  let paraBuffer = [];

  const flushPara = (key) => {
    if (paraBuffer.length) { blocks.push(renderBlock(paraBuffer.join(" "), `p${key}`)); paraBuffer = []; }
  };
  const flushList = (key) => {
    if (listBuffer.length) {
      blocks.push(<ul key={`ul${key}`} className="list-disc pl-5 space-y-1">{listBuffer.map((li, i) => <li key={i}>{li}</li>)}</ul>);
      listBuffer = [];
    }
  };

  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) { flushPara(i); flushList(i); return; }
    if (trimmed.startsWith("### ")) { flushPara(i); flushList(i); blocks.push(<h3 key={i} className="font-display text-lg mt-6 mb-1">{trimmed.slice(4)}</h3>); }
    else if (trimmed.startsWith("## ")) { flushPara(i); flushList(i); blocks.push(<h2 key={i} className="font-display text-xl mt-8 mb-2">{trimmed.slice(3)}</h2>); }
    else if (trimmed.startsWith("# ")) { flushPara(i); flushList(i); blocks.push(<h1 key={i} className="font-display text-2xl mt-8 mb-2">{trimmed.slice(2)}</h1>); }
    else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) { flushPara(i); listBuffer.push(trimmed.slice(2)); }
    else { flushList(i); paraBuffer.push(trimmed); }
  });
  flushPara("end"); flushList("end");
  return <div className="space-y-3 text-sm text-foreground/85">{blocks}</div>;
}

export default function LegalDocPage() {
  const { docType } = useParams();
  const [doc, setDoc] = useState(undefined); // undefined = loading, null = not found

  useEffect(() => {
    setDoc(undefined);
    api.get(`/legal/${docType}`).then(({ data }) => setDoc(data)).catch(() => setDoc(null));
  }, [docType]);

  if (doc === undefined) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  if (doc === null) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-center gap-2 p-6">
        <div className="font-display text-2xl">Not available</div>
        <div className="text-sm text-muted-foreground max-w-sm">This document hasn't been published yet.</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-2xl mx-auto px-6 py-16">
        <Link to="/" className="text-xs text-muted-foreground hover:text-foreground">&larr; Back</Link>
        <h1 className="font-display text-3xl tracking-tight mt-4">{doc.title}</h1>
        <div className="text-xs text-muted-foreground mt-2">
          Version {doc.version} · effective {doc.published_at ? new Date(doc.published_at).toLocaleDateString() : "—"}
        </div>
        <div className="mt-8">
          <MarkdownLite content={doc.content} />
        </div>
      </div>
    </div>
  );
}

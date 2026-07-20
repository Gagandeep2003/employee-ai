import React from "react";

export const H1 = ({ eyebrow, title, children }) => (
  <div className="mb-6 flex items-end justify-between gap-4 flex-wrap">
    <div>
      {eyebrow && <div className="text-[10px] uppercase tracking-[0.3em] text-accent mb-1">{eyebrow}</div>}
      <h1 className="font-display text-3xl md:text-4xl tracking-tight">{title}</h1>
    </div>
    {children && <div className="flex gap-2">{children}</div>}
  </div>
);

export const Card = ({ title, children, actions, className = "" }) => (
  <div className={`bg-card border border-border rounded-lg ${className}`}>
    {title && (
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{title}</div>
        {actions}
      </div>
    )}
    <div>{children}</div>
  </div>
);

export const KPI = ({ label, value, sub, accent, testid }) => (
  <div className={`bg-card border rounded-lg p-4 ${accent ? "border-accent/50" : "border-border"}`} data-testid={testid}>
    <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</div>
    <div className="font-display text-2xl md:text-3xl mt-2 tracking-tight">{value}</div>
    {sub && <div className="text-[11px] text-muted-foreground mt-1">{sub}</div>}
  </div>
);

export const Btn = ({ children, onClick, variant = "default", disabled, testid, className = "" }) => {
  const styles = {
    default: "bg-primary text-primary-foreground hover:bg-accent hover:text-accent-foreground",
    ghost: "border border-border hover:bg-secondary",
    danger: "bg-destructive text-destructive-foreground hover:opacity-90",
    accent: "bg-accent text-accent-foreground hover:opacity-90",
  }[variant];
  return (
    <button data-testid={testid} onClick={onClick} disabled={disabled}
      className={`px-3 py-1.5 rounded-md text-xs transition-colors disabled:opacity-50 ${styles} ${className}`}>
      {children}
    </button>
  );
};

export const Row = ({ children }) => <tr className="border-b border-border hover:bg-secondary/40 transition-colors">{children}</tr>;
export const Th = ({ children, className = "" }) => (
  <th className={`text-left p-3 text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-medium ${className}`}>{children}</th>
);
export const Td = ({ children, className = "" }) => <td className={`p-3 text-sm ${className}`}>{children}</td>;

export const Search = ({ value, onChange, placeholder = "Search…", testid = "admin-search" }) => (
  <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} data-testid={testid}
    className="px-3 py-1.5 rounded-md border border-border bg-card text-sm outline-none focus:ring-2 focus:ring-primary min-w-[240px]" />
);

export const Pill = ({ children, tone = "default" }) => {
  const t = {
    default: "bg-secondary text-foreground",
    accent: "bg-accent/20 text-accent",
    warn: "bg-orange-500/20 text-orange-300",
    danger: "bg-destructive/20 text-red-300",
    ok: "bg-green-500/20 text-green-300",
  }[tone];
  return <span className={`text-[10px] uppercase tracking-[0.15em] px-2 py-0.5 rounded ${t}`}>{children}</span>;
};

export const fmtINR = (n) => `₹${(n || 0).toLocaleString()}`;
export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString() : "—");
export const fmtDT = (s) => (s ? new Date(s).toLocaleString() : "—");

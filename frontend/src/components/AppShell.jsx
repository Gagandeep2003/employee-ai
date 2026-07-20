import React, { useEffect, useState, createContext, useContext } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setAuthToken } from "../lib/api";
import { useAuth } from "../lib/auth";
import { toast } from "sonner";
import { Users, ChatCircleText, BookOpen, ChartLine, PaintBrush, CreditCard, Handshake, GearSix, ShieldCheck, SignOut, Buildings, House, CalendarCheck, EnvelopeSimple, X, Package } from "@phosphor-icons/react";

export const BizCtx = createContext({ businesses: [], current: null, setCurrent: () => {} });
export const useBiz = () => useContext(BizCtx);

function VerifyEmailBanner({ user }) {
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  if (!user || user.email_verified || dismissed) return null;

  const resend = async () => {
    setSending(true);
    try {
      await api.post("/auth/verify-email/resend");
      toast.success("Verification email sent");
    } catch {
      toast.error("Couldn't send it -- try again shortly");
    }
    setSending(false);
  };

  return (
    <div className="bg-accent/10 border-b border-accent/30 px-4 py-2 flex items-center justify-between text-xs" data-testid="verify-email-banner">
      <div className="flex items-center gap-2 text-accent-foreground/90">
        <EnvelopeSimple size={14} /> Please verify your email ({user.email}) to keep full access.
      </div>
      <div className="flex items-center gap-3">
        <button onClick={resend} disabled={sending} data-testid="resend-verify" className="text-accent hover:underline">
          {sending ? "Sending…" : "Resend email"}
        </button>
        <button onClick={() => setDismissed(true)} aria-label="Dismiss" className="text-muted-foreground hover:text-foreground">
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

export default function AppShell() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [businesses, setBusinesses] = useState([]);
  const [current, setCurrent] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.get("/businesses").then(({ data }) => {
      setBusinesses(data);
      const stored = localStorage.getItem("current_biz");
      const c = data.find((b) => b.business_id === stored) || data[0] || null;
      setCurrent(c);
      setLoaded(true);
      if (!data.length) nav("/onboarding", { replace: true });
    }).catch(() => setLoaded(true));
  }, []);

  useEffect(() => { if (current) localStorage.setItem("current_biz", current.business_id); }, [current]);

  const logout = async () => { await api.post("/auth/logout"); setAuthToken(null); window.location.href = "/"; };

  const links = [
    { to: "/dashboard", label: "Dashboard", Icon: House },
    { to: "/conversations", label: "Conversations", Icon: ChatCircleText },
    { to: "/knowledge", label: "Knowledge", Icon: BookOpen },
    { to: "/appointments", label: "Appointments", Icon: CalendarCheck },
    { to: "/inventory", label: "Inventory", Icon: Package },
    { to: "/analytics", label: "Analytics", Icon: ChartLine },
    { to: "/widget-settings", label: "Widget", Icon: PaintBrush },
    { to: "/billing", label: "Billing", Icon: CreditCard },
    { to: "/referrals", label: "Referrals", Icon: Handshake },
    { to: "/settings", label: "Settings", Icon: GearSix },
  ];
  const isAdmin = user?.role === "admin";

  if (!loaded) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading workspace…</div>;

  return (
    <BizCtx.Provider value={{ businesses, current, setCurrent, refresh: () => api.get("/businesses").then(({ data }) => setBusinesses(data)) }}>
      <div className="dark min-h-screen bg-background text-foreground flex" data-testid="app-shell">
        <aside className="w-64 border-r border-border bg-card flex flex-col">
          <div className="p-5 border-b border-border">
            <div className="font-display text-xl tracking-tight">AI Employee</div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-[0.2em] mt-1">Business Console</div>
          </div>
          <div className="p-3 border-b border-border">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mb-1">Business</div>
            <select
              data-testid="biz-selector"
              className="w-full bg-secondary text-secondary-foreground text-sm px-2 py-2 rounded-md border border-border"
              value={current?.business_id || ""}
              onChange={(e) => setCurrent(businesses.find((b) => b.business_id === e.target.value))}
            >
              {businesses.map((b) => (
                <option key={b.business_id} value={b.business_id}>{b.name}</option>
              ))}
            </select>
            <button
              onClick={() => nav("/onboarding")}
              data-testid="add-business-btn"
              className="mt-2 text-xs text-accent hover:underline flex items-center gap-1">
              <Buildings size={14} /> Add business
            </button>
          </div>
          <nav className="flex-1 p-2 space-y-1">
            {links.map(({ to, label, Icon }) => (
              <NavLink
                key={to} to={to} data-testid={`nav-${label.toLowerCase()}`}
                className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-secondary"}`}
              >
                <Icon size={17} weight="duotone" /> {label}
              </NavLink>
            ))}
          </nav>
          <div className="p-3 border-t border-border">
            {isAdmin && (
              <button onClick={() => nav("/admin")} data-testid="enter-admin"
                className="w-full text-xs flex items-center gap-2 px-3 py-2 rounded-md bg-accent/10 border border-accent/30 text-accent hover:bg-accent hover:text-accent-foreground transition-colors mb-3">
                <ShieldCheck size={14} /> Admin console
              </button>
            )}
            <div className="flex items-center gap-2 mb-2">
              {user?.picture && <img src={user.picture} alt="" className="w-7 h-7 rounded-full" />}
              <div className="text-xs">
                <div className="font-medium truncate max-w-[150px]">{user?.name}</div>
                <div className="text-muted-foreground truncate max-w-[150px]">{user?.email}</div>
              </div>
            </div>
            <button onClick={logout} data-testid="logout-btn" className="w-full text-xs flex items-center gap-2 px-3 py-2 rounded-md hover:bg-secondary transition-colors">
              <SignOut size={14} /> Sign out
            </button>
          </div>
        </aside>
        <main className="flex-1 overflow-y-auto">
          <VerifyEmailBanner user={user} />
          <Outlet />
        </main>
      </div>
    </BizCtx.Provider>
  );
}

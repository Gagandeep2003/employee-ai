import React, { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { api, setAuthToken } from "../lib/api";
import {
  ChartLineUp, Buildings, UsersThree, Receipt, Robot, Chats, BookOpen, Globe, Handshake,
  Tag, Ticket, Broadcast, Flag, Pulse, ClipboardText, GearSix, SignOut, ArrowSquareOut
} from "@phosphor-icons/react";

const LINKS = [
  { to: "/admin", label: "Executive", Icon: ChartLineUp, end: true },
  { to: "/admin/businesses", label: "Businesses", Icon: Buildings },
  { to: "/admin/users", label: "Users", Icon: UsersThree },
  { to: "/admin/subscriptions", label: "Subscriptions", Icon: Receipt },
  { to: "/admin/ai-usage", label: "AI Usage", Icon: Robot },
  { to: "/admin/conversations", label: "Conversations", Icon: Chats },
  { to: "/admin/knowledge", label: "Knowledge", Icon: BookOpen },
  { to: "/admin/crawls", label: "Crawlers", Icon: Globe },
  { to: "/admin/referrals", label: "Referrals", Icon: Handshake },
  { to: "/admin/coupons", label: "Coupons", Icon: Tag },
  { to: "/admin/tickets", label: "Tickets", Icon: Ticket },
  { to: "/admin/broadcasts", label: "Broadcasts", Icon: Broadcast },
  { to: "/admin/flags", label: "Feature Flags", Icon: Flag },
  { to: "/admin/system", label: "System", Icon: Pulse },
  { to: "/admin/audit", label: "Audit Log", Icon: ClipboardText },
  { to: "/admin/settings", label: "Settings", Icon: GearSix },
];

export default function AdminShell() {
  const { user } = useAuth();
  const nav = useNavigate();
  const logout = async () => { await api.post("/auth/logout"); setAuthToken(null); window.location.href = "/"; };

  return (
    <div className="dark min-h-screen bg-background text-foreground flex" data-testid="admin-shell">
      <aside className="w-60 border-r border-border bg-card flex flex-col">
        <div className="p-5 border-b border-border">
          <div className="font-display text-xl tracking-tight">AI Employee</div>
          <div className="text-[10px] uppercase tracking-[0.25em] text-accent mt-1">Admin Console</div>
        </div>
        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {LINKS.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to} to={to} end={end}
              data-testid={`admin-nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-secondary"}`
              }
            >
              <Icon size={16} weight="duotone" /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <button onClick={() => nav("/dashboard")} data-testid="exit-admin"
            className="w-full text-xs flex items-center gap-2 px-3 py-2 rounded-md hover:bg-secondary transition-colors mb-1">
            <ArrowSquareOut size={14} /> Exit to business view
          </button>
          <div className="text-[11px] px-3 py-1">
            <div className="font-medium truncate">{user?.name}</div>
            <div className="text-muted-foreground truncate">{user?.email}</div>
          </div>
          <button onClick={logout} data-testid="admin-logout"
            className="w-full text-xs flex items-center gap-2 px-3 py-2 rounded-md hover:bg-secondary transition-colors">
            <SignOut size={14} /> Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}

import React, { useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./lib/auth";

import Landing from "./pages/Landing";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import VerifyEmail from "./pages/VerifyEmail";
import Onboarding from "./pages/Onboarding";
import DashboardHome from "./pages/DashboardHome";
import Conversations from "./pages/Conversations";
import KnowledgeBase from "./pages/KnowledgeBase";
import Appointments from "./pages/Appointments";
import Inventory from "./pages/Inventory";
import Analytics from "./pages/Analytics";
import WidgetSettings from "./pages/WidgetSettings";
import Billing from "./pages/Billing";
import Referrals from "./pages/Referrals";
import Settings from "./pages/Settings";
import Admin from "./pages/Admin";
import AdminShell from "./components/AdminShell";
import AdminExecutive from "./pages/admin/Executive";
import AdminBusinesses from "./pages/admin/Businesses";
import AdminUsers from "./pages/admin/Users";
import AdminSubscriptions from "./pages/admin/Subscriptions";
import AdminAIUsage from "./pages/admin/AIUsage";
import AdminConversations from "./pages/admin/ConversationsExplorer";
import AdminKnowledge from "./pages/admin/KnowledgeManager";
import AdminCrawlers from "./pages/admin/Crawlers";
import AdminReferrals from "./pages/admin/Referrals";
import AdminCoupons from "./pages/admin/Coupons";
import AdminTickets from "./pages/admin/Tickets";
import AdminBroadcasts from "./pages/admin/Broadcasts";
import AdminFlags from "./pages/admin/FeatureFlags";
import AdminSystem from "./pages/admin/SystemMonitor";
import AdminAudit from "./pages/admin/AuditLog";
import AdminSettings from "./pages/admin/Settings";
import WidgetPage from "./pages/WidgetPage";
import TalkPage from "./pages/TalkPage";
import AppShell from "./components/AppShell";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/widget/:businessId" element={<WidgetPage />} />
      <Route path="/talk/:businessId" element={<TalkPage />} />
      <Route path="/onboarding" element={<Protected><Onboarding /></Protected>} />
      <Route element={<Protected><AppShell /></Protected>}>
        <Route path="/dashboard" element={<DashboardHome />} />
        <Route path="/conversations" element={<Conversations />} />
        <Route path="/knowledge" element={<KnowledgeBase />} />
        <Route path="/appointments" element={<Appointments />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/widget-settings" element={<WidgetSettings />} />
        <Route path="/billing" element={<Billing />} />
        <Route path="/referrals" element={<Referrals />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route element={<Protected><AdminShell /></Protected>}>
        <Route path="/admin" element={<AdminExecutive />} />
        <Route path="/admin/businesses" element={<AdminBusinesses />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/subscriptions" element={<AdminSubscriptions />} />
        <Route path="/admin/ai-usage" element={<AdminAIUsage />} />
        <Route path="/admin/conversations" element={<AdminConversations />} />
        <Route path="/admin/knowledge" element={<AdminKnowledge />} />
        <Route path="/admin/crawls" element={<AdminCrawlers />} />
        <Route path="/admin/referrals" element={<AdminReferrals />} />
        <Route path="/admin/coupons" element={<AdminCoupons />} />
        <Route path="/admin/tickets" element={<AdminTickets />} />
        <Route path="/admin/broadcasts" element={<AdminBroadcasts />} />
        <Route path="/admin/flags" element={<AdminFlags />} />
        <Route path="/admin/system" element={<AdminSystem />} />
        <Route path="/admin/audit" element={<AdminAudit />} />
        <Route path="/admin/settings" element={<AdminSettings />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRouter />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

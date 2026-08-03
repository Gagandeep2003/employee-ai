import { useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import { toast } from "sonner";

/** basePath: "/auth/mfa" for any signed-in user, "/admin/mfa" for the admin-only variant
 * (kept for backward compatibility -- both hit the same backend logic under the hood). */
export function useMfa(basePath = "/auth/mfa") {
  const { user, refresh } = useAuth();
  const [setup, setSetup] = useState(null); // { secret, provisioning_uri }
  const [busy, setBusy] = useState(false);

  const startSetup = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`${basePath}/setup`);
      setSetup(data);
      return true;
    } catch {
      toast.error("Couldn't start two-factor setup");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const confirmSetup = async (code) => {
    setBusy(true);
    try {
      await api.post(`${basePath}/enable`, { code });
      toast.success("Two-factor authentication enabled");
      setSetup(null);
      await refresh();
      return true;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Incorrect code");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const disable = async (password) => {
    setBusy(true);
    try {
      await api.post(`${basePath}/disable`, { password });
      toast.success("Two-factor authentication disabled");
      await refresh();
      return true;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Incorrect password");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const cancelSetup = () => setSetup(null);

  return { user, setup, busy, startSetup, confirmSetup, disable, cancelSetup };
}

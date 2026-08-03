import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const ORIGIN = process.env.REACT_APP_BACKEND_URL;

const TOKEN_KEY = "ai_employee_token";

// NOTE: normal login/signup relies entirely on the httpOnly session cookie the
// backend sets -- it is NOT readable by JS, which is what makes it resistant to
// XSS. setAuthToken/getAuthToken exist ONLY for the admin "impersonate business"
// flow (see pages/admin/Businesses.jsx), which deliberately hands back a bearer
// token so the admin panel can open a session as that business's owner in the
// same tab. Nothing else in the app should call setAuthToken.
export const setAuthToken = (t) => {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
};
export const getAuthToken = () => (typeof localStorage !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null);

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Only attaches a Bearer token when one was explicitly set via setAuthToken
// (impersonation). Everyday auth flows through the cookie automatically.
api.interceptors.request.use((config) => {
  const t = getAuthToken();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

// Paths where a 401 is a meaningful, final answer (wrong password, no session yet,
// or the refresh call itself) rather than "the access token expired mid-session" --
// these must NOT trigger a refresh-and-retry, or a wrong password would silently
// turn into an infinite refresh loop.
const NO_REFRESH_RETRY_PATHS = ["/auth/login", "/auth/signup", "/auth/refresh", "/auth/mfa/verify"];

let refreshInFlight = null;

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;
    const path = (original.url || "").split("?")[0];
    const skip = getAuthToken() || original._retried || NO_REFRESH_RETRY_PATHS.some((p) => path.startsWith(p));

    if (status !== 401 || skip) return Promise.reject(error);

    original._retried = true;
    try {
      if (!refreshInFlight) {
        refreshInFlight = api.post("/auth/refresh").finally(() => { refreshInFlight = null; });
      }
      await refreshInFlight;
      return api(original);
    } catch {
      return Promise.reject(error); // refresh itself failed -- surface the original 401
    }
  }
);

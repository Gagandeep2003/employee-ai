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

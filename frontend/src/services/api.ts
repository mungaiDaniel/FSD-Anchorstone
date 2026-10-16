import axios from "axios";
import { clearTokens, getAccessToken, setMustChangePassword } from "@/lib/auth";
import { API, ROUTES } from "@/lib/constants";

// ============================================================================
// Single axios instance for every API call.
// - Adds the JWT to each request.
// - 401 on any call other than sign-in: session is over → back to /login.
// - 403 PASSWORD_CHANGE_REQUIRED: the account is on a temporary password →
//   the mandatory change-password screen (the API refuses everything else).
// ============================================================================

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:4455/api/v1",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const code = error.response?.data?.code;
    const isLoginCall = String(error.config?.url ?? "").endsWith(API.LOGIN);

    if (status === 401 && !isLoginCall) {
      clearTokens();
      // Full reload so no stale state from the previous session survives.
      window.location.href = ROUTES.LOGIN;
    } else if (status === 403 && code === "PASSWORD_CHANGE_REQUIRED") {
      setMustChangePassword(true);
      if (window.location.pathname !== ROUTES.CHANGE_PASSWORD) window.location.href = ROUTES.CHANGE_PASSWORD;
    }
    return Promise.reject(error);
  }
);

export default api;

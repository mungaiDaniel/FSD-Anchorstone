import type { UserRole } from "./types";

// ============================================================================
// Session storage — the JWT plus display info. No investor data is stored here.
// The role is only used to show/hide UI; the API re-checks it on every call.
// ============================================================================

const TOKEN_KEY = "anchorstone_access_token";
const ROLE_KEY = "anchorstone_user_role";
const NAME_KEY = "anchorstone_user_name";
const EMAIL_KEY = "anchorstone_user_email";
const MUST_CHANGE_KEY = "anchorstone_must_change_password";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return read(TOKEN_KEY);
}

export function getUserRole(): UserRole | null {
  const role = read(ROLE_KEY);
  return role === "user" || role === "admin" || role === "super_admin" ? role : null;
}

export function getUserName(): string | null {
  return read(NAME_KEY);
}

export function getUserEmail(): string | null {
  return read(EMAIL_KEY);
}

export function getMustChangePassword(): boolean {
  return read(MUST_CHANGE_KEY) === "1";
}

export function setMustChangePassword(value: boolean): void {
  try {
    if (value) localStorage.setItem(MUST_CHANGE_KEY, "1");
    else localStorage.removeItem(MUST_CHANGE_KEY);
  } catch {
    /* storage unavailable */
  }
}

export function setSession(token: string, role: string, name: string, email: string, mustChangePassword: boolean): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role);
  localStorage.setItem(NAME_KEY, name);
  localStorage.setItem(EMAIL_KEY, email);
  setMustChangePassword(mustChangePassword);
}

export function clearTokens(): void {
  for (const key of [TOKEN_KEY, ROLE_KEY, NAME_KEY, EMAIL_KEY, MUST_CHANGE_KEY]) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* storage unavailable */
    }
  }
}

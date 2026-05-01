// Token lives in localStorage so refreshes survive. This is fine for a
// self-hosted internal Heroku — for multi-tenant SaaS you'd use httpOnly
// cookies and a CSRF token.

const KEY = "liftwork.token";

export function getToken(): string | null {
  return localStorage.getItem(KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(KEY);
}

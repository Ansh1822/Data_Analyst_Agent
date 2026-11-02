// Empty in local dev (Vite proxies /api). On Vercel set VITE_API_URL to your backend URL, no trailing slash.
export const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

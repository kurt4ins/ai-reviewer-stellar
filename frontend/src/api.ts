const TOKEN_KEY = "stellar_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(`/api${path}`, { ...options, headers });
  if (resp.status === 204) return undefined as T;

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    if (resp.status === 401) clearToken();
    const detail =
      typeof data?.detail === "string" ? data.detail : `ошибка ${resp.status}`;
    throw new ApiError(resp.status, detail);
  }
  return data as T;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Repo {
  id: string;
  provider: "github" | "gitlab";
  owner: string;
  name: string;
  webhook_secret: string;
  webhook_url: string;
  ignore_globs: string[];
  block_critical_merge: boolean;
  dialog_enabled: boolean;
}

export interface ReviewSummary {
  id: string;
  repository_id: string;
  repo_full_name: string;
  provider: "github" | "gitlab";
  pr_number: number;
  commit_sha: string;
  status: string;
  findings_count: number;
  critical_count: number;
  created_at: string;
}

export interface Finding {
  id: string;
  file_path: string;
  line_number: number;
  cwe: string;
  severity: string;
  description: string;
  fix_code: string | null;
  fix_explanation: string | null;
  confidence: number;
}

export interface ReviewDetail extends ReviewSummary {
  findings: Finding[];
}

export const api = {
  register: (email: string, password: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  listRepos: () => request<Repo[]>("/repos"),
  createRepo: (provider: string, owner: string, name: string) =>
    request<Repo>("/repos", {
      method: "POST",
      body: JSON.stringify({ provider, owner, name }),
    }),
  updateRepo: (id: string, patch: Partial<Repo>) =>
    request<Repo>(`/repos/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteRepo: (id: string) =>
    request<void>(`/repos/${id}`, { method: "DELETE" }),
  listReviews: (repoId?: string) =>
    request<ReviewSummary[]>(
      `/reviews${repoId ? `?repo_id=${repoId}` : ""}`,
    ),
  getReview: (id: string) => request<ReviewDetail>(`/reviews/${id}`),
};

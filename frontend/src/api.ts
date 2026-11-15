export type OperationsSection = "imports" | "timesheets" | "discrepancies" | "batches";
export interface OperationsRecord { id: number; project: string; reference: string; source_row: number | null }
import type { ChatReply, Conversation } from "./chat";
export interface Session {
  username: string;
  role: string;
  permissions: string[];
  project_permissions: Record<string, string[]>;
  csrf_token: string;
  demo_mode: boolean;
  must_change_password: boolean;
}
export interface Project { id: number; name: string }
export interface Settings { demo_mode: boolean; ollama_model: string; report_integration?: { status: string; missing: string[] } }

export interface OllamaStatus {
  model: string;
  status: "ready" | "model_missing" | "unreachable";
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

const base = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export async function rawRequest(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(base + path, { ...init, credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? "Request failed");
  }
  return response;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await rawRequest(path, init);
  return response.status === 204 ? (undefined as T) : response.json();
}

export interface DocumentRecord { id: string; project_id: number | null; filename: string; rows: number; status: string; sha256: string }
export interface ConversationWorkflow {
  stage: string;
  scope?: { project_id: number; source_ids: string[]; source_rows: number };
  scope_fresh?: boolean;
  mapping?: { id: string; version: number; fingerprint: string; status: string; effective_status?: string;
    confirmation_method?: string;
    categories: Record<string, string[]>;
    sheets: { file_id: string; filename: string; sheet_index: number; kind: string;
      headers: string[]; columns: Record<string, number> }[] } | null;
  validation?: { status: string; run_id?: number; started_at?: string; completed_at?: string; error_code?: string } | null;
  blockers?: string[];
}
export const documentDownload = (id: string) => `${base}/documents/${id}/download`;

export const api = {
  workflowState: (conversation: string) => request<ConversationWorkflow>(`/chat/conversations/${conversation}/workflow`),
  confirmMapping: (conversation: string, proposal: string, version: number, fingerprint: string,
    sheets: { file_id: string; sheet_index: number; kind: string; columns: Record<string, number> }[], csrf: string) =>
    request<{ message: string; workflow: ConversationWorkflow }>(`/chat/conversations/${conversation}/mappings/${proposal}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ version, fingerprint, sheets }),
    }),
  documentMetrics: () => request<{ documents: number; source_rows: number }>("/documents/metrics"),
  documents: (conversation?: string) => request<DocumentRecord[]>(conversation ? `/documents?conversation_id=${conversation}` : "/documents"),
  uploadDocument: (project: number | undefined, conversation: string, file: File, csrf: string) =>
    request<DocumentRecord>(`/documents?${new URLSearchParams({ ...(project === undefined ? {} : { project_id: String(project) }), conversation_id: conversation, filename: file.name })}`, {
      method: "POST", headers: { "X-CSRF-Token": csrf, "Content-Type": file.type || "application/octet-stream" }, body: file,
    }),
  session: () => request<Session>("/auth/session"),
  login: (username: string, password: string) => request<Session>("/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  }),
  logout: (csrf: string) => request<void>("/auth/logout", {
    method: "POST", headers: { "X-CSRF-Token": csrf },
  }),
  conversations: () => request<Conversation[]>("/chat/conversations"),
  conversation: (id: string) => request<Conversation>(`/chat/conversations/${id}`),
  createConversation: (csrf: string) => request<Conversation>("/chat/conversations", {
    method: "POST", headers: { "X-CSRF-Token": csrf },
  }),
  assistantActivity: (id: string, requestId: string) =>
    request<{ steps: string[] }>(`/chat/conversations/${id}/activity/${requestId}`),
  sendMessage: (id: string, message: string, csrf: string, requestId: string, projectId?: number) =>
    request<ChatReply>(`/chat/conversations/${id}/messages`, {
      method: "POST", headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json" },
      body: JSON.stringify({ message, request_id: requestId, project_id: projectId }),
    }),
  operations: (section: OperationsSection) => request<OperationsRecord[]>(`/operations/${section}`),
  renameConversation: (id: string, title: string, csrf: string) => request<Conversation>(`/chat/conversations/${id}`, {
    method: "PATCH", headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json" }, body: JSON.stringify({ title }),
  }),
  deleteConversation: (id: string, csrf: string) => request<void>(`/chat/conversations/${id}`, {
    method: "DELETE", headers: { "X-CSRF-Token": csrf },
  }),
  aiStatus: () => request<OllamaStatus>("/ai/status"),
  projects: () => request<Project[]>("/projects"),
  settings: () => request<Settings>("/settings"),
};

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Could not reach the local API.";
}

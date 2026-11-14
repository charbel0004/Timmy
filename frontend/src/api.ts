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
export interface Settings { demo_mode: boolean; ollama_model: string }

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

export interface DocumentRecord { id: string; project_id: number; filename: string; rows: number; status: string; sha256: string }
export const documentDownload = (id: string) => `${base}/documents/${id}/download`;

export const api = {
  documentMetrics: () => request<{ documents: number; source_rows: number }>("/documents/metrics"),
  documents: (conversation?: string) => request<DocumentRecord[]>(conversation ? `/documents?conversation_id=${conversation}` : "/documents"),
  uploadDocument: (project: number, conversation: string, file: File, csrf: string) =>
    request<DocumentRecord>(`/documents?${new URLSearchParams({ project_id: String(project), conversation_id: conversation, filename: file.name })}`, {
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
  sendMessage: (id: string, message: string, csrf: string, requestId: string) =>
    request<ChatReply>(`/chat/conversations/${id}/messages`, {
      method: "POST", headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json" },
      body: JSON.stringify({ message, request_id: requestId }),
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

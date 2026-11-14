import type { Project } from "./api";

export interface ChatTable { title: string; columns: string[]; rows: string[][] }
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: string;
  attachments?: string[];
  tables?: ChatTable[];
}
export interface ChatRequest {
  conversationId: string;
  message: string;
  projectId?: Project["id"];
  files: File[];
}
export interface ChatReply {
  message: ChatMessage & { role: "assistant" };
  proposedActions?: { id: string; label: string }[];
}
export type ChatTransport = (request: ChatRequest) => Promise<ChatReply>;

export interface Conversation { id: string; title?: string | null; messages: ChatMessage[] }

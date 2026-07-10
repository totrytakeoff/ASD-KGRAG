export interface GraphNode {
  id: string;
  name: string;
  type: string; // Disease / Drug / AssessmentTool / Intervention / Symptom / ...
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string; // MEASURED_BY / INDICATED_FOR / COMORBID_WITH ...
  source_type?: string;
  target_type?: string;
  support_count?: number;
  confidence?: number;
}

export type QaProfile = "fast" | "balanced" | "deep";
export type QaStatus =
  | "routing"
  | "retrieving"
  | "followup_retrieval"
  | "waiting_model"
  | "retrying"
  | "generating"
  | "done"
  | "degraded"
  | "cancelled";

export interface QaTiming {
  retrieve_sec?: number;
  prompt_build_sec?: number;
  prompt_chars?: number;
  llm_sec?: number;
  api_total_sec?: number;
  first_token_sec?: number | null;
  retry_count?: number;
  cache_hit?: boolean;
  profile?: string;
}

export interface Citation {
  citation_id: string; // C1
  title?: string;
  year?: number | string;
  evidence_level?: string;
  retrieval?: string; // graph-evidence / graph+vector / vector
  score?: number;
}

export interface AiMessage {
  role: "ai";
  content: string; // Markdown 回答
  relations?: GraphEdge[]; // 图谱证据路径
  nodes?: GraphNode[];
  citations?: Citation[];
  retrieved_at?: string;
  profile?: QaProfile;
  status?: QaStatus;
  timing?: QaTiming;
  degraded?: boolean;
}

export interface UserMessage {
  role: "user";
  content: string;
}

export type Message = UserMessage | AiMessage;

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  updated_at: string;
}

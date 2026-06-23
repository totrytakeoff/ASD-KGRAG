export interface GraphNode {
  id: string;
  name: string;
  type: string; // Disease / Drug / AssessmentTool / Intervention / Symptom / ...
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string; // MEASURED_BY / INDICATED_FOR / COMORBID_WITH ...
  support_count?: number;
  confidence?: number;
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

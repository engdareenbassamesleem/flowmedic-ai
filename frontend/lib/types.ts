export type IncidentStatus = "open" | "diagnosed";
export type Severity = "medium" | "high";
export type RiskLevel = "low" | "medium" | "high";

export interface Diagnosis {
  summary: string;
  probable_root_cause: string;
  affected_component: string;
  recommended_fix: string;
  confidence: number;
  risk_level: RiskLevel;
}

export interface Incident {
  id: string;
  workflow_id: string;
  workflow_name: string;
  execution_id: string;
  failed_node: string | null;
  error_type: string;
  error_message: string;
  execution_timestamp: string | null;
  severity: Severity;
  status: IncidentStatus;
  diagnosis: Diagnosis | null;
  diagnosis_provider: string | null;
}

export interface Workflow {
  id: string;
  name: string;
  active: boolean;
}

export interface IncidentPage {
  data: Incident[];
}

export interface WorkflowPage {
  data: Workflow[];
  next_cursor: string | null;
}

export interface HealthResponse {
  status: "ok";
}

export interface N8nConnectionResponse {
  connected: boolean;
}

export interface SystemStatus {
  n8n_configured: boolean;
  ai_mode: "mock" | "configured";
  database_engine: string;
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string };
}

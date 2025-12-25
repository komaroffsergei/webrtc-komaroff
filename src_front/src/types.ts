export type ServerEventType = "info" | "error" | "warning";
export interface AgentCommand {
  type: "SHOW_AIRPORTS" | "SET_POSITION" | "BUILD_ROUTE" | "SHOW_ERROR_MESSAGE";
  params?: {
    artifact_key?: string;
    message?: string;
    [key: string]: unknown;
  };
}

export interface AgentData {
  command: AgentCommand;
  artifacts: Record<string, unknown>;
}

export interface AgentMessage {
  status: "OK" | "FAILED" | "UNSUPPORTED_REQUEST";
  model: string;
  prompt: string;
  steps: number;
  result: Record<string, any>;
  total_time_sec: number;
  data: AgentData;
}


export interface ServerEvent {
  time: string;
  service: string;
  type: ServerEventType;
  name: "message" | "log";
  message: AgentMessage;
  uid: string;
}

export type AGentClientCommands =
  | "SHOW_AIRPORTS"
  | "SET_POSITION"
  | "BUILD_ROUTE"
  | "SHOW_ERROR_MESSAGE";

export type AgentErrorStatus = "TOOLS_EXCEPTION" |
    "LLM_EXCEPTION" |
    "MAX_STEPS_EXCEEDED" |
    "UNSUPPORTED_REQUEST"




export type AgentCommandContext = {
  chat: {
    addMessage(text: string, role: "user" | "server" | "status" | "thinking"): void;
  };
  warning: {
    show(payload: { message: string }): void;
  };
};

export interface AgentCommand {
  type: AGentClientCommands
  params?: {
    artifact_key?: string;
    message?: string;
    [key: string]: unknown;
  };
}

// export interface AgentData {
//   command: AgentCommand;
//   artifacts: Record<string, unknown>;
// }

export interface AgentMessage {
  success: boolean;
  client_handler: AgentClientHandler;
  error?: {
      type: AgentErrorStatus,
      message: string
  },
  data?: {
    model: string;
    prompt: string;
    steps: number;
    total_time_sec: number;
  };
  result?: Record<string, any|any[]>;
}

export interface AgentClientHandler {
  artifacts: {
    all: string[],
    last: string,
    payload: Record<string, any|any[]>
  },
  command: "SHOW_AIRPORTS" | "SET_POSITION" | "BUILD_ROUTE" | "SHOW_ERROR_MESSAGE"
}


export interface ServerEvent {
  time: string;
  service: string;
  kind: "message" | "log" | "error" | "control";
  name: string,
  message: AgentMessage | string;
  uid: string;
}

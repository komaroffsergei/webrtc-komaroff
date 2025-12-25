export type AgentCommandType =
  | "SHOW_AIRPORTS"
  | "SET_POSITION"
  | "BUILD_ROUTE"
  | "SHOW_ERROR_MESSAGE";

export type AgentCommand = {
  type: AgentCommandType | string;
  params?: Record<string, unknown>;
};

export type AgentResponse = {
  status?: string;
  model?: string;
  prompt?: string;
  steps?: number;
  result?: unknown;
  data?: {
    command?: AgentCommand;
    artifacts?: Record<string, unknown>;
  };
};

export type AgentCommandContext = {
  chat: {
    addMessage(text: string, role: "user" | "server" | "status" | "thinking"): void;
  };
  warning: {
    show(payload: { message: string }): void;
  };
};

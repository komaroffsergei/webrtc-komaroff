export type AgentCommandContext = {
  chat: {
    addMessage(text: string, role: "user" | "server" | "status" | "thinking"): void;
  };
  warning: {
    show(payload: { message: string }): void;
  };
};

export type ServerEvent = {
  time: string;
  service: string;
  type: string;
  kind: string;
  data: Record<string, unknown>;
  name: string;
  uid: string;
};

export const KnownEventTypes = {
  log: "log",
  command: "command",
} as const;

export type KnownEventType = (typeof KnownEventTypes)[keyof typeof KnownEventTypes];

export function isKnownEventType(value: string): value is KnownEventType {
  return value === KnownEventTypes.log || value === KnownEventTypes.command;
}

export type EventArtifacts = {
  all: string[];
  last: string | null;
  payload: Record<string, unknown>;
};

export type ClientHandlerCommand = {
  command: string;
  artifacts?: EventArtifacts;
};

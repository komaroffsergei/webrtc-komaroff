export type ChatMessageOptions = {
  turnId?: string;
  linkedUserTurnId?: string;
  editable?: boolean;
};

export type AgentCommandContext = {
  chat: {
    addMessage(
      text: string,
      role: "user" | "server" | "status" | "thinking",
      options?: ChatMessageOptions,
    ): void;
  };
  warning: {
    show(payload: { message: string }): void;
  };
  map?: {
    setAirports(airports: Array<{ lat: number; lon: number; id?: string; code?: string; name?: string; status?: string }>): void;
    setCurrentPosition(lat: number, lon: number): void;
    drawRoute(route: { geometry: Array<[number, number]>; distance_km?: number }): void;
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

export type HistoryTurn = {
  turn_id: string;
  role: string;
  text: string;
  ts_ms: number;
  meta?: Record<string, unknown>;
};

export type HistorySnapshotResponse = {
  ok?: unknown;
  items?: unknown;
  runtime_context?: unknown;
  error?: unknown;
  session_id?: unknown;
};

export type MessageEditPayload = {
  turn_id: string;
};

export type MessageRequestPayload = {
  text: string;
  turn_id: string;
  session_id: string | null;
  edit?: MessageEditPayload;
};

export type CommandRequestTelemetryEvent = {
  phase: "start" | "done" | "error";
  endpoint: "/core/message";
  request: MessageRequestPayload;
  response_status?: number;
  response_body?: Record<string, unknown> | null;
  session_id_after?: string | null;
  error?: string;
};

export type ReplayFlowItem = {
  source: "http" | "nats" | "client";
  action: string;
  service?: string;
  turn_id?: string | null;
  edit_turn_id?: string | null;
  phase?: "start" | "done" | "error";
  mode?: string;
  command?: string;
  scenario?: string;
  workflow?: string;
  text?: string;
  prompt?: string;
  missing?: string[];
  extracted?: Record<string, unknown>;
  status_code?: number;
  blocked?: boolean;
  error?: string;
  details?: Record<string, unknown>;
};

export type ReplayBundle = {
  schema: "dialog_replay@2";
  session_id: string | null;
  trigger: string;
  flow: ReplayFlowItem[];
  dropped: number;
};

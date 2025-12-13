export type ServerLogEntry = {
  time?: string;
  service?: string;
  type?: string;
  message?: string;
};

export type ServerEvent =
  | { name?: string; service?: string; type?: string; message?: unknown; time?: string }
  | { type: "command"; method?: string; params?: unknown; uid?: string }
  | { type: "message"; descr?: string; text?: string }
  | { type: "warning"; descr?: string };

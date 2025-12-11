export type ServerLogEntry = {
  time?: string;
  service: string;
  type: string;
  message: string;
  name?: string;
  [key: string]: unknown;
};

export type CommandPayload = {
  type?: string;
  descr?: string;
  method?: string;
  params?: unknown;
  uid?: string;
  text?: string;
  [key: string]: unknown;
};

export type ModelEvent =
  | {
      name: "model_downloading_status";
      type: "info" | "error";
      message: string;
    }
  | {
      name: "model_downloading_percent";
      message: number;
    };

export type ServerEvent = ServerLogEntry & CommandPayload & Partial<ModelEvent>;

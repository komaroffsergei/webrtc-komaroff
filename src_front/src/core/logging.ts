import {ServerEvent} from "../types";

export function logEvent(event: ServerEvent): void {
  const title = `[${event.service}] ${formatEventTag(event)}`;
  const method = pickConsoleMethod(event);
  const group = `${title} uid=${event.uid}`;
  console.groupCollapsed(group);
  method("meta", {
    service: event.service,
    type: event.type,
    kind: event.kind,
    name: event.name,
    uid: event.uid,
    time: event.time,
  });

  const trace = readTrace(event.data);
  if (trace) {
    method("trace", trace);
  }
  const payload = unwrapPayload(event.data);
  if (event.name === "llm_request_debug" && payload) {
    method("llm.request", payload);
  } else if (event.name === "llm_result" && payload) {
    method("llm.result", payload);
  } else {
    method("data", event.data);
  }
  console.groupEnd();
}


export function logError(name: string, val: any) {
  console.error(name, val);
}

export function logReplayBundle(bundle: unknown): void {
  console.debug("[dialog.replay.bundle]", clone(bundle));
}


function pickConsoleMethod(event: ServerEvent): (...args: unknown[]) => void {
  if (event.type === "log" && event.kind === "error") return console.error;
  if (event.type === "log" && event.kind === "warn") return console.warn;
  if (isLlmEvent(event)) return console.info;
  return console.debug;
}


function readTrace(data: Record<string, unknown>): Record<string, unknown> | null {
  const trace = data.trace;
  if (!trace || typeof trace !== "object") return null;
  return trace as Record<string, unknown>;
}


function unwrapPayload(data: Record<string, unknown>): Record<string, unknown> | null {
  const payload = data.payload;
  if (!payload || typeof payload !== "object") return null;
  return payload as Record<string, unknown>;
}


function formatEventTag(event: ServerEvent): string {
  const base = `${event.type}/${event.kind}`;
  const namePart = event.name ? `:${event.name}` : "";
  if (event.kind === "client") {
    const command = event.data.command;
    if (typeof command === "string" && command.trim()) {
      return `${base}:${command.trim()}${namePart}`;
    }
  }
  return `${base}${namePart}`;
}


function isLlmEvent(event: ServerEvent): boolean {
  return event.name === "llm_request_debug" || event.name === "llm_result";
}

function clone<T>(value: T): T {
  try {
    return JSON.parse(JSON.stringify(value)) as T;
  } catch {
    return value;
  }
}

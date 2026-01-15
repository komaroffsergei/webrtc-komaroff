import {appConfig} from "../config/appConfig"
import {ServerEvent} from "../types";

export function logEvent(event: ServerEvent): void {
  let logFn;
  if (["log"].includes(event.kind)) {
    logFn = console.log;
  } else if (["error"].includes(event.kind)) {
    logFn = console.warn;
  } else if (["message", "control"].includes(event.kind)) {
    logFn = console.info;
  } else {
    logFn = console.error;
  }

  logFn(
    `${event.time}: [${event.service}]${event.kind ? "(" + event.kind + ")" : ""}) ${event.name ? event.name + " = " : ""}${formatMessage(event.message)}`
  );
}


export function logError(name: string, val: any) {
  console.error(name, val);
}


function formatMessage(msg: unknown): string {
  if (typeof msg === "string") return msg;

  try {
    return JSON.stringify(msg, null, 2);
  } catch {
    return String(msg);
  }
}

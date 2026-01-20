import {ServerEvent} from "../types";

export function logEvent(event: ServerEvent): void {
  const logFn =
    event.type === "log" && event.kind === "error"
      ? console.warn
      : event.type === "log"
        ? console.log
        : event.type === "command"
          ? console.info
          : console.error;

  logFn(
    `${event.time}: [${event.service}] type=${event.type} kind=${event.kind}${event.name ? ` name=${event.name}` : ""} data=${formatValue(event.data)} uid=${event.uid}`
  );
}


export function logError(name: string, val: any) {
  console.error(name, val);
}


function formatValue(val: unknown): string {
  if (typeof val === "string") return val;

  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}

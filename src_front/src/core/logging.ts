import type { ServerLogEntry } from "./types";
import {appConfig} from "../config/appConfig"
export function logEvent(entry: ServerLogEntry | ServerLogEntry[]): void {
  const list = Array.isArray(entry) ? entry : [entry];

  for (const e of list) {
    const time = e.time ?? new Date().toISOString();
    const service = e.service ?? "client";
    const type = e.type ?? "info";
    const message = e.message ?? "";

    const level = type.toLowerCase();
    const writer =
      (console as unknown as Record<string, (...args: unknown[]) => void>)[level] ?? console.log;

    writer(`${time} [${service}] [${type}] ${message}`);
  }
}


export function logError(name: string, val: any) {
  console.error(name, val);
}


export function debug() {

}
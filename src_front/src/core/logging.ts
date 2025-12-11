import type { ServerLogEntry } from "../types";

type LogListener = (entry: ServerLogEntry) => void;

export class Logger {
  private listeners = new Set<LogListener>();

  addListener(listener: LogListener): void {
    this.listeners.add(listener);
  }

  removeListener(listener: LogListener): void {
    this.listeners.delete(listener);
  }

  emit(entry: ServerLogEntry): void {
    const enriched: ServerLogEntry = {
      time: entry.time ?? new Date().toISOString(),
      ...entry,
    };

    if (enriched.service && enriched.type && enriched.message) {
      const level = enriched.type.toLowerCase();
      const writer = (
        console as unknown as Record<string, (...args: unknown[]) => void>
      )[level];
      (writer ?? console.log)(
        `${enriched.time} [${enriched.service}] [${enriched.type}] ${enriched.message}`,
      );
    }

    this.listeners.forEach((listener) => {
      try {
        listener(enriched);
      } catch (err) {
        console.warn("[logger] listener failed", err);
      }
    });
  }
}

export const logger = new Logger();

export function logEvent(entry: ServerLogEntry | ServerLogEntry[]): void {
  if (Array.isArray(entry)) {
    entry.forEach((item) => logger.emit(item));
    return;
  }
  logger.emit(entry);
}

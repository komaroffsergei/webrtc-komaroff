import type { CommandRequestTelemetryEvent, MessageRequestPayload } from "../types";

type CommandHandlerFn = (params: unknown, uid?: string) => void | Promise<void>;
const DEFAULT_MESSAGE_TIMEOUT_MS = 70000;

export class CommandHandler {
  private handlers = new Map<string, CommandHandlerFn>();
  private sessionId: string | null = null;
  private telemetryHook: ((event: CommandRequestTelemetryEvent) => void) | null = null;

  register(method: string, handler: CommandHandlerFn): void {
    this.handlers.set(method, handler);
  }

  setSessionId(sessionId: string | null): void {
    this.sessionId = sessionId;
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  setTelemetryHook(hook: ((event: CommandRequestTelemetryEvent) => void) | null): void {
    this.telemetryHook = hook;
  }

  // async handleServerEvent(event: ServerEvent): Promise<boolean> {
  //   if (event && "type" in event && event.type === "command" && event.method) {
  //     const h = this.handlers.get(event.method);
  //     if (!h) {
  //       logEvent({ service: "command", type: "warn", message: `No handler for ${event.method}` });
  //       return true;
  //     }
  //     try {
  //       await h(event.params, event.uid);
  //     } catch (err) {
  //       logEvent({
  //         service: "command",
  //         type: "error",
  //         message: `Handler ${event.method} failed: ${err instanceof Error ? err.message : String(err)}`,
  //       });
  //     }
  //     return true;
  //   }
  //
  //   return false;
  // }

  async sendMessage(text: string, turnId: string): Promise<string | null> {
    return this.postMessage({
      text,
      turn_id: turnId,
      session_id: this.sessionId,
    });
  }

  async sendEditedMessage(text: string, turnId: string): Promise<string | null> {
    return this.postMessage({
      text,
      turn_id: turnId,
      session_id: this.sessionId,
      edit: { turn_id: turnId },
    });
  }

  private async postMessage(request: MessageRequestPayload): Promise<string | null> {
    this.emitTelemetry({
      phase: "start",
      endpoint: "/core/message",
      request: copyRequest(request),
    });

    let resp: Response;
    const timeoutMs = resolveMessageTimeoutMs();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      resp = await fetch("/core/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });
    } catch (err) {
      const normalizedError = normalizeTransportError(err, timeoutMs);
      this.emitTelemetry({
        phase: "error",
        endpoint: "/core/message",
        request: copyRequest(request),
        error: errorMessage(normalizedError),
      });
      throw normalizedError;
    } finally {
      window.clearTimeout(timeoutId);
    }

    let data: unknown = null;
    try {
      data = await resp.json();
    } catch {
      data = null;
    }

    const responseBody = toRecord(data);
    const nextSessionId = typeof responseBody?.session_id === "string" ? responseBody.session_id : this.sessionId;

    if (!resp.ok) {
      const message = `Server responded with ${resp.status}`;
      this.emitTelemetry({
        phase: "error",
        endpoint: "/core/message",
        request: copyRequest(request),
        response_status: resp.status,
        response_body: responseBody,
        session_id_after: nextSessionId,
        error: message,
      });
      throw new Error(message);
    }

    this.sessionId = nextSessionId;
    this.emitTelemetry({
      phase: "done",
      endpoint: "/core/message",
      request: copyRequest(request),
      response_status: resp.status,
      response_body: responseBody,
      session_id_after: this.sessionId,
    });
    return this.sessionId;
  }

  private emitTelemetry(event: CommandRequestTelemetryEvent): void {
    if (!this.telemetryHook) return;
    try {
      this.telemetryHook(event);
    } catch (err) {
      console.debug("[command.telemetry] handler failed", err);
    }
  }
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message || error.name || "Error";
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function copyRequest(request: MessageRequestPayload): MessageRequestPayload {
  return {
    text: request.text,
    turn_id: request.turn_id,
    session_id: request.session_id,
    ...(request.edit ? { edit: { turn_id: request.edit.turn_id } } : {}),
  };
}

function resolveMessageTimeoutMs(): number {
  const raw = (window as any)?.SETTINGS?.MESSAGE_REQUEST_TIMEOUT_MS;
  const numeric = typeof raw === "string" ? Number(raw) : (typeof raw === "number" ? raw : NaN);
  if (!Number.isFinite(numeric)) return DEFAULT_MESSAGE_TIMEOUT_MS;
  const bounded = Math.max(5000, Math.min(300000, Math.round(numeric)));
  return bounded;
}

function normalizeTransportError(error: unknown, timeoutMs: number): Error {
  if (error instanceof DOMException && error.name === "AbortError") {
    return new Error(`Request timeout after ${timeoutMs}ms`);
  }
  if (error instanceof Error) return error;
  return new Error(errorMessage(error));
}

import type { ServerEvent } from "../types";
import { logEvent } from "./logging";

type CommandHandlerFn = (params: unknown, uid?: string) => void | Promise<void>;

export class CommandHandler {
  private handlers = new Map<string, CommandHandlerFn>();

  register(method: string, handler: CommandHandlerFn): void {
    this.handlers.set(method, handler);
    logEvent({
      service: "command",
      type: "info",
      message: `Registered handler for ${method}`,
    });
  }

  async execute(method: string, params: unknown, uid?: string): Promise<void> {
    const handler = this.handlers.get(method);
    if (!handler) {
      logEvent({
        service: "command",
        type: "warn",
        message: `No handler for ${method}`,
      });
      return;
    }
    try {
      await handler(params, uid);
    } catch (err) {
      logEvent({
        service: "command",
        type: "error",
        message: `Handler ${method} failed: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }

  async handleServerEvent(event: ServerEvent): Promise<boolean> {
    if (event.type === "command" && event.method) {
      await this.execute(event.method, event.params, event.uid);
      return true;
    }

    if (event.type === "message" && event.descr === "send" && event.text) {
      logEvent({
        service: "command",
        type: "info",
        message: `Message from server: ${event.text}`,
      });
      return false;
    }

    if (event.type === "warning" && typeof event.descr === "string") {
      logEvent({
        service: "command",
        type: "warning",
        message: event.descr,
      });
      return true;
    }

    return false;
  }

  async sendMessage(text: string): Promise<void> {
    const resp = await fetch("/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (!resp.ok) {
      throw new Error(`Server responded with ${resp.status}`);
    }
  }
}

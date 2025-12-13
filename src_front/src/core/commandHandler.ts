import type { ServerEvent } from "./types";
import { logEvent } from "./logging";

type CommandHandlerFn = (params: unknown, uid?: string) => void | Promise<void>;

export class CommandHandler {
  private handlers = new Map<string, CommandHandlerFn>();

  register(method: string, handler: CommandHandlerFn): void {
    this.handlers.set(method, handler);
    logEvent({ service: "command", type: "info", message: `Registered ${method}` });
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

  async sendMessage(text: string): Promise<void> {
    const resp = await fetch("/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) throw new Error(`Server responded with ${resp.status}`);
  }
}

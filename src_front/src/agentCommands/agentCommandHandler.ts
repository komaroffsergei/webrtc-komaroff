import type { AgentCommandContext, AgentResponse } from "./types";
import { commandHandlers } from "./commands";

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

export class AgentCommandHandler {
  constructor(private ctx: AgentCommandContext) {}

  isAgentCommandEvent(x: unknown): x is AgentResponse {
    if (!isRecord(x)) return false;
    const data = x["data"];
    if (!isRecord(data)) return false;
    const command = data["command"];
    if (!isRecord(command)) return false;
    return typeof command["type"] === "string" && command["type"].length > 0;
  }

  handle(x: unknown): void {
    if (!this.isAgentCommandEvent(x)) return;

    const resp = x as AgentResponse;
    const type = String(resp.data?.command?.type ?? "");

    const handler = commandHandlers[type];
    if (!handler) {
      this.ctx.chat.addMessage(`Неизвестная команда: ${type}`, "status");
      return;
    }

    try {
      handler(resp, this.ctx);
    } catch (err) {
      // чтобы фронт не умирал от одного кривого поля в JSON
      this.ctx.chat.addMessage(
        `Ошибка обработки команды ${type}: ${String(err)}`,
        "status",
      );
    }
  }
}

import { commandHandlers } from "./commands";
import {AgentCommandContext, AgentMessage} from "../types";

export class AgentCommandHandler {
  constructor(private ctx: AgentCommandContext) {}


  handle(event: AgentMessage): void {
    const command = String(event.client_handler?.command ?? "");

    const handler = commandHandlers[command];
    if (!handler) {
      this.ctx.chat.addMessage(`Неизвестная команда: ${command}`, "status");
      return;
    }

    try {
      handler(event, this.ctx);
    } catch (err) {
      // чтобы фронт не умирал от одного кривого поля в JSON
      this.ctx.chat.addMessage(
        `Ошибка обработки команды ${command}: ${String(err)}`,
        "status",
      );
    }
  }
}

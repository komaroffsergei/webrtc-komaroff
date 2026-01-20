import { commandHandlers } from "./commands";
import {AgentCommandContext, ClientHandlerCommand} from "../types";

export class AgentCommandHandler {
  constructor(private ctx: AgentCommandContext) {}


  handle(event: ClientHandlerCommand): void {
    const command = String(event.command ?? "");

    const handler = commandHandlers[command];
    if (!handler) {
      this.ctx.chat.addMessage(`Неизвестная команда: ${command}`, "status");
      return;
    }

    try {
      handler(event, this.ctx);
    } catch (err) {
      this.ctx.chat.addMessage(
        `Ошибка обработки команды ${command}: ${String(err)}`,
        "status",
      );
    }
  }
}

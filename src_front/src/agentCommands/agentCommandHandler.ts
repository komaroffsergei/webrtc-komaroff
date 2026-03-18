import type { AgentCommandContext, ClientHandlerCommand } from "../types";
import { handleBuildRoute } from "./commands/buildRoute";
import { handleSetAirports } from "./commands/setAirports";
import { handleSetPosition } from "./commands/setPosition";
import { handleShowAirports } from "./commands/showAirports";
import { handleShowErrorMessage } from "./commands/showErrorMessage";
import { handleShowMessage } from "./commands/showMessage";

type CommandHandlerFn = (resp: ClientHandlerCommand, ctx: AgentCommandContext) => void;

const commandHandlers: Record<string, CommandHandlerFn> = {
  SHOW_AIRPORTS: handleShowAirports,
  SET_AIRPORTS: handleSetAirports,
  SET_POSITION: handleSetPosition,
  BUILD_ROUTE: handleBuildRoute,
  SHOW_ERROR_MESSAGE: handleShowErrorMessage,
  ASK_USER_INPUT: handleShowMessage,
  SHOW_MESSAGE: handleShowMessage,
};

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

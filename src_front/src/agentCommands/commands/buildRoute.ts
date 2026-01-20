import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export function handleBuildRoute(
  _resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  ctx.chat.addMessage("BUILD_ROUTE: заглушка (пока не реализовано).", "status");
}

import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export function handleSetPosition(
  _resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  ctx.chat.addMessage("SET_POSITION: заглушка (пока не реализовано).", "status");
}

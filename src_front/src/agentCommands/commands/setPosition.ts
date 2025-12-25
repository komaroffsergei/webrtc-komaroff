import {AgentCommandContext, AgentMessage} from "../../types";

export function handleSetPosition(
  _resp: AgentMessage,
  ctx: AgentCommandContext,
): void {
  ctx.chat.addMessage("SET_POSITION: заглушка (пока не реализовано).", "status");
}

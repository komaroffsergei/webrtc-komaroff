import type { AgentCommandContext, AgentResponse } from "../types";

export function handleSetPosition(
  _resp: AgentResponse,
  ctx: AgentCommandContext,
): void {
  ctx.chat.addMessage("SET_POSITION: заглушка (пока не реализовано).", "status");
}

import type { AgentCommandContext, AgentResponse } from "../types";

export function handleBuildRoute(
  _resp: AgentResponse,
  ctx: AgentCommandContext,
): void {
  ctx.chat.addMessage("BUILD_ROUTE: заглушка (пока не реализовано).", "status");
}

import {AgentCommandContext, AgentMessage} from "../../types";

export function handleBuildRoute(
  _resp: AgentMessage,
  ctx: AgentCommandContext,
): void {
  ctx.chat.addMessage("BUILD_ROUTE: заглушка (пока не реализовано).", "status");
}

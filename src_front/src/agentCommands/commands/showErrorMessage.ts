import {AgentCommandContext, AgentMessage} from "../../types";

export function handleShowErrorMessage(
  resp: AgentMessage,
  ctx: AgentCommandContext,
): void {
  const msg = resp.error?.message || resp.error?.type || "Неизвестная ошибка";

  ctx.chat.addMessage(`Ошибка: ${String(msg)}`, "server");
}

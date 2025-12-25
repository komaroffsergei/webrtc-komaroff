import type { AgentCommandContext, AgentResponse } from "../types";

export function handleShowErrorMessage(
  resp: AgentResponse,
  ctx: AgentCommandContext,
): void {
  const cmd = resp.data?.command;

  const msg =
    (resp.result as any)?.error ??
    (cmd?.params?.message as string | undefined) ??
    (resp as any)?.message ??
    "Неизвестная ошибка";

  ctx.chat.addMessage(`Ошибка: ${String(msg)}`, "server");
}

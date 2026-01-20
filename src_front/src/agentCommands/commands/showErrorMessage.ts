import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export function handleShowErrorMessage(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const artifacts = resp.artifacts?.payload ?? {};
  const last = resp.artifacts?.last;
  const payload = last && artifacts[last] ? (artifacts[last] as Record<string, unknown>) : {};
  const msg = payload.message ?? payload.summary ?? "Неизвестная ошибка";

  ctx.chat.addMessage(`Ошибка: ${String(msg)}`, "server");
}

import {AgentCommandContext, ClientHandlerCommand} from "../../types";
import { readLastArtifactPayload } from "./payload";

export function handleShowErrorMessage(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const payload = readLastArtifactPayload(resp);
  const msg = payload.message ?? payload.summary ?? "Неизвестная ошибка";
  const assistantTurnId = typeof payload.assistant_turn_id === "string" ? payload.assistant_turn_id : undefined;
  const userTurnId = typeof payload.user_turn_id === "string" ? payload.user_turn_id : undefined;

  ctx.chat.addMessage(`Ошибка: ${String(msg)}`, "server", { turnId: assistantTurnId, linkedUserTurnId: userTurnId });
}

import {AgentCommandContext, ClientHandlerCommand} from "../../types";
import { readLastArtifactPayload } from "./payload";

export function handleShowMessage(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const payload = readLastArtifactPayload(resp);
  const summary = payload?.summary ?? payload?.prompt ?? payload?.message;
  const text =
    typeof summary === "string"
      ? summary
      : "Message received.";
  const assistantTurnId = typeof payload.assistant_turn_id === "string" ? payload.assistant_turn_id : undefined;
  const userTurnId = typeof payload.user_turn_id === "string" ? payload.user_turn_id : undefined;

  ctx.chat.addMessage(text, "server", { turnId: assistantTurnId, linkedUserTurnId: userTurnId });
}

import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export function handleShowMessage(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const artifacts = resp.artifacts?.payload ?? {};
  const last = resp.artifacts?.last;
  const payload = last && artifacts[last] ? (artifacts[last] as Record<string, unknown>) : {};
  const summary = payload?.summary ?? payload?.prompt ?? payload?.message;
  const text =
    typeof summary === "string"
      ? summary
      : "Message received.";

  ctx.chat.addMessage(text, "server");
}

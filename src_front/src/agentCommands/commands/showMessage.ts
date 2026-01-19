import {AgentCommandContext, AgentMessage} from "../../types";

export function handleShowMessage(
  resp: AgentMessage,
  ctx: AgentCommandContext,
): void {
  const artifacts = resp.client_handler?.artifacts?.payload ?? {};
  const last = resp.client_handler?.artifacts?.last;
  const payload = last && artifacts[last] ? artifacts[last] as Record<string, unknown> : {};
  const summary = payload?.summary ?? payload?.prompt ?? payload?.message;
  const text =
    typeof summary === "string"
      ? summary
      : typeof resp.result === "string"
        ? resp.result
        : "Message received.";

  ctx.chat.addMessage(text, "server");
}

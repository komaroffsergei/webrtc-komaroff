import type { AssistantElements } from "./elements";

export function setStatus(el: AssistantElements, text: string): void {
  if (el.connectionStatus) el.connectionStatus.textContent = text;
}

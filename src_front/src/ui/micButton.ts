import type { AssistantElements } from "./elements";

export function bindMicButton(
  el: AssistantElements,
  onToggle: () => void | Promise<void>,
): void {
  el.micButton?.addEventListener("click", () => {
    el.chatWindow?.classList.toggle("expanded");
    void onToggle();
  });
}

export type ChatRole = "user" | "server" | "status" | "thinking";

export class ChatUI {
  constructor(private root: HTMLElement) {}

  addMessage(text: string, role: ChatRole): void {
    const div = document.createElement("div");
    div.className = `message ${role}-message`;
    div.textContent = text;
    this.root.appendChild(div);
    this.root.scrollTop = this.root.scrollHeight;
  }

  addThinking(): string {
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `thinking-${Date.now()}-${Math.random().toString(16).slice(2)}`;

    const div = document.createElement("div");
    div.className = "message thinking-message";
    div.dataset.thinkingId = id;

    const dots = document.createElement("span");
    dots.className = "thinking-dots";
    dots.setAttribute("aria-label", "Агент думает");
    div.appendChild(dots);

    this.root.appendChild(div);
    this.root.scrollTop = this.root.scrollHeight;

    return id;
  }

  removeThinking(id: string | null): void {
    if (!id) return;
    const el = this.root.querySelector(
      `[data-thinking-id="${CSS.escape(id)}"]`,
    );
    el?.remove();
  }
}

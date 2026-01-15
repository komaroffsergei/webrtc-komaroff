export type ChatRole = "user" | "server" | "status" | "thinking";

export class ChatUI {
  private thinkingCount = 0;

  constructor(
    private root: HTMLElement,
    private textInput?: HTMLInputElement | null,
  ) {}

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

    this.thinkingCount += 1;
    this.setInputBlocked(true);

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
    if (!el) return;
    el.remove();
    this.thinkingCount = Math.max(0, this.thinkingCount - 1);
    if (this.thinkingCount === 0) {
      this.setInputBlocked(false);
    }
  }

  private setInputBlocked(blocked: boolean): void {
    if (!this.textInput) return;
    this.textInput.disabled = blocked;
    if (blocked) {
      this.textInput.blur();
    }
  }
}

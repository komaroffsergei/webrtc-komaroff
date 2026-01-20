export type ChatRole = "user" | "server" | "status" | "thinking";

export type ThinkingMeta = {
  scenario?: { id: string; reason?: string };
  tools?: string[];
};

export class ChatUI {
  private thinkingActive = false;
  private voiceBlocked = false;
  private thinkingEl: HTMLElement | null = null;

  constructor(
    private root: HTMLElement,
    private textInput?: HTMLInputElement | null,
    private micButton?: HTMLButtonElement | null,
  ) {}

  addMessage(text: string, role: ChatRole): void {
    const div = document.createElement("div");
    div.className = `message ${role}-message`;
    div.textContent = text;
    this.root.appendChild(div);
    this.root.scrollTop = this.root.scrollHeight;
  }

  setThinking(summaryText: string, fullText?: string, meta?: ThinkingMeta): void {
    if (!this.thinkingEl) {
      const div = document.createElement("div");
      div.className = "message thinking-message";

      const dots = document.createElement("span");
      dots.className = "thinking-dots";
      dots.setAttribute("aria-label", "Thinking");
      div.appendChild(dots);

      const box = document.createElement("div");
      box.className = "thinking-box";

      const summary = document.createElement("div");
      summary.className = "thinking-summary";
      box.appendChild(summary);

      const metaEl = document.createElement("div");
      metaEl.className = "thinking-meta";
      box.appendChild(metaEl);

      const details = document.createElement("div");
      details.className = "thinking-details";
      box.appendChild(details);

      div.appendChild(box);

      this.root.appendChild(div);
      this.thinkingEl = div;
    }

    const summaryEl = this.thinkingEl.querySelector(".thinking-summary");
    if (summaryEl) summaryEl.textContent = summaryText;

    const metaEl = this.thinkingEl.querySelector(".thinking-meta");
    if (metaEl) metaEl.textContent = this.formatThinkingMeta(meta);

    const detailsEl = this.thinkingEl.querySelector(".thinking-details");
    if (detailsEl) detailsEl.textContent = fullText ? fullText : "";

    this.thinkingActive = true;
    this.updateBlockedState();
    this.root.scrollTop = this.root.scrollHeight;
  }

  updateThinking(summaryText: string, fullText?: string, meta?: ThinkingMeta): void {
    this.setThinking(summaryText, fullText, meta);
  }

  clearThinking(): void {
    if (this.thinkingEl) {
      this.thinkingEl.remove();
      this.thinkingEl = null;
    }
    this.thinkingActive = false;
    this.updateBlockedState();
  }

  setVoiceBlocked(blocked: boolean): void {
    this.voiceBlocked = blocked;
    this.updateBlockedState();
  }

  private updateBlockedState(): void {
    const blocked = this.thinkingActive || this.voiceBlocked;
    if (this.textInput) {
      this.textInput.disabled = blocked;
      if (blocked) {
        this.textInput.blur();
      }
    }
    if (this.micButton) {
      this.micButton.disabled = blocked;
    }
  }

  private formatThinkingMeta(meta?: ThinkingMeta): string {
    if (!meta) return "";
    const parts: string[] = [];
    if (meta.scenario?.id) {
      parts.push(
        meta.scenario.reason
          ? `Scenario: ${meta.scenario.id} (${meta.scenario.reason})`
          : `Scenario: ${meta.scenario.id}`,
      );
    }
    if (meta.tools && meta.tools.length) {
      parts.push(`Tools: ${meta.tools.join(", ")}`);
    }
    return parts.join("\n");
  }
}

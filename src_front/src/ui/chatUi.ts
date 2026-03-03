import type { ChatMessageOptions, HistoryTurn } from "../types";

export type ChatRole = "user" | "server" | "status" | "thinking";

export type ThinkingMeta = {
  scenario?: { id: string; reason?: string };
  tools?: string[];
};

type EditHandler = (turnId: string, text: string) => void | Promise<void>;

export class ChatUI {
  private thinkingActive = false;
  private voiceBlocked = false;
  private editInFlight = false;
  private thinkingEl: HTMLElement | null = null;
  private messageByTurn = new Map<string, HTMLElement>();
  private editHandler: EditHandler | null = null;
  private activeInlineEditor: HTMLElement | null = null;

  constructor(
    private root: HTMLElement,
    private textInput?: HTMLInputElement | null,
    private micButton?: HTMLButtonElement | null,
  ) {}

  setEditHandler(handler: EditHandler): void {
    this.editHandler = handler;
  }

  addMessage(text: string, role: ChatRole, options?: ChatMessageOptions): void {
    const div = document.createElement("div");
    div.className = `message ${role}-message`;
    div.dataset.role = role;
    if (options?.turnId) {
      div.dataset.turnId = options.turnId;
      this.messageByTurn.set(options.turnId, div);
    }
    if (options?.linkedUserTurnId) {
      div.dataset.linkedUserTurnId = options.linkedUserTurnId;
    }

    const textEl = document.createElement("div");
    textEl.className = "message-text";
    textEl.textContent = text;
    div.appendChild(textEl);

    if (role === "user" && options?.turnId && options?.editable) {
      const actions = document.createElement("div");
      actions.className = "message-actions";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "message-edit-btn";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => {
        this.openInlineEditor(div, options.turnId as string, textEl, actions);
      });

      actions.appendChild(editBtn);
      div.appendChild(actions);
    }

    this.root.appendChild(div);
    this.root.scrollTop = this.root.scrollHeight;
  }

  restoreHistory(turns: HistoryTurn[]): void {
    for (const turn of turns) {
      if (!turn?.turn_id || typeof turn.turn_id !== "string") continue;
      if (this.messageByTurn.has(turn.turn_id)) continue;
      if (turn.role === "user") {
        this.addMessage(turn.text, "user", {
          turnId: turn.turn_id,
          editable: true,
        });
      } else if (turn.role === "assistant") {
        const linkedUserTurnId = typeof turn.meta?.user_turn_id === "string" ? turn.meta.user_turn_id : undefined;
        this.addMessage(turn.text, "server", {
          turnId: turn.turn_id,
          linkedUserTurnId,
        });
      }
    }
  }

  rewriteFromUserTurn(turnId: string, newText: string): boolean {
    const target = this.messageByTurn.get(turnId);
    if (!target || target.dataset.role !== "user") {
      return false;
    }

    const textEl = target.querySelector(".message-text");
    if (textEl) {
      textEl.textContent = newText;
    }

    let node = target.nextElementSibling as HTMLElement | null;
    while (node) {
      const next = node.nextElementSibling as HTMLElement | null;
      const nodeTurnId = node.dataset.turnId;
      if (nodeTurnId) {
        this.messageByTurn.delete(nodeTurnId);
      }
      node.remove();
      node = next;
    }
    this.clearThinking();
    this.root.scrollTop = this.root.scrollHeight;
    return true;
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

  finishThinking(): void {
    if (!this.thinkingEl) return;

    if (!this.hasRichThinkingContent(this.thinkingEl)) {
      this.clearThinking();
      return;
    }

    const dots = this.thinkingEl.querySelector(".thinking-dots");
    if (dots) {
      dots.remove();
    }
    this.thinkingEl.classList.add("thinking-message-complete");
    this.thinkingEl = null;
    this.thinkingActive = false;
    this.updateBlockedState();
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

  private openInlineEditor(
    wrapper: HTMLElement,
    turnId: string,
    textEl: Element,
    actions: HTMLElement,
  ): void {
    if (!this.editHandler) return;
    if (this.isAgentBusy()) return;
    if (this.activeInlineEditor) return;

    const currentText = (textEl.textContent || "").trim();
    actions.style.display = "none";

    const editor = document.createElement("div");
    editor.className = "message-edit-row";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "message-edit-input";
    input.value = currentText;

    const save = document.createElement("button");
    save.type = "button";
    save.className = "message-edit-save";
    save.textContent = "Save";

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "message-edit-cancel";
    cancel.textContent = "Cancel";

    const closeEditor = () => {
      editor.remove();
      actions.style.display = "";
      this.activeInlineEditor = null;
    };

    save.addEventListener("click", async () => {
      const value = input.value.trim();
      if (!value || value === currentText) {
        closeEditor();
        return;
      }
      save.disabled = true;
      input.disabled = true;
      cancel.disabled = true;
      this.editInFlight = true;
      this.updateBlockedState();
      closeEditor();
      try {
        await this.editHandler?.(turnId, value);
      } finally {
        this.editInFlight = false;
        this.updateBlockedState();
      }
    });
    cancel.addEventListener("click", closeEditor);

    editor.appendChild(input);
    editor.appendChild(save);
    editor.appendChild(cancel);
    wrapper.appendChild(editor);
    this.activeInlineEditor = editor;
    input.focus();
    input.select();
  }

  private updateBlockedState(): void {
    const blocked = this.isAgentBusy();
    if (this.textInput) {
      this.textInput.disabled = blocked;
      if (blocked) {
        this.textInput.blur();
      }
    }
    if (this.micButton) {
      this.micButton.disabled = blocked;
    }
    this.root.querySelectorAll<HTMLButtonElement>(".message-edit-btn").forEach((btn) => {
      btn.disabled = blocked;
    });
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

  private hasRichThinkingContent(el: HTMLElement): boolean {
    const details = (el.querySelector(".thinking-details") as HTMLElement | null)?.textContent?.trim() ?? "";
    const meta = (el.querySelector(".thinking-meta") as HTMLElement | null)?.textContent?.trim() ?? "";
    return Boolean(details || meta);
  }

  private isAgentBusy(): boolean {
    return this.thinkingActive || this.voiceBlocked || this.editInFlight;
  }
}

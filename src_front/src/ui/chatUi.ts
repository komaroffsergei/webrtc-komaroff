export type ChatMessageType = "server" | "user" | "status";

export class ChatUI {
  private logEl: HTMLElement;

  constructor(target: HTMLElement) {
    this.logEl = target;
  }

  addMessage(text: string, type: ChatMessageType = "server", uid?: string): void {
    const message = document.createElement("div");
    message.className = `message ${type}-message`;
    message.textContent = text;
    if (uid) {
      message.dataset.uid = uid;
    }
    this.logEl.appendChild(message);
    this.scrollToBottom();
  }

  clear(): void {
    this.logEl.innerHTML = "";
  }

  private scrollToBottom(): void {
    const chatWindow = document.querySelector(".chat-window");
    if (chatWindow?.classList.contains("expanded")) {
      setTimeout(() => {
        this.logEl.scrollTop = this.logEl.scrollHeight;
      }, 50);
    }
  }
}

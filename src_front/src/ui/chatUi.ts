export type ChatRole = "user" | "server" | "status";

export class ChatUI {
  constructor(private root: HTMLElement) {}

  addMessage(text: string, role: ChatRole): void {
    const div = document.createElement("div");
    div.className = `message ${role}-message`;
    div.textContent = text;
    this.root.appendChild(div);
    this.root.scrollTop = this.root.scrollHeight;
  }
}

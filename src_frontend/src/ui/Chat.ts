import { isDebugMode } from '../utils/debug-mode';
import {natsClient} from "../App";


export class ChatUI {
  private container: HTMLElement;
  private logEl: HTMLElement;
  private inputEl: HTMLInputElement;
  private expanded = false;

  constructor() {
    this.container = document.querySelector('.chat-window')!;
    this.logEl = document.getElementById('messageLog')!;
    this.inputEl = document.getElementById('textInput')! as HTMLInputElement;

    this.inputEl.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        const text = this.inputEl.value.trim();
        if (text) {
          this.addUserMessage(text);
          this.inputEl.value = '';
          this.sendTextToAgent(text);
        }
      }
    });

    // клик по чату раскрывает его
    this.container.addEventListener('click', () => {
      if (!this.expanded) this.toggle(true);
    });
  }

  toggle(expand: boolean): void {
    this.expanded = expand;
    this.container.classList.toggle('expanded', expand);
    if (expand) {
      this.scrollToBottom();
    }
  }

  addUserMessage(text: string): void {
    this.addMessage(text, 'user');
  }

  addServerMessage(text: string): void {
    this.addMessage(text, 'server');
  }

  private addMessage(text: string, role: 'user' | 'server'): void {
    const div = document.createElement('div');
    div.className = `message ${role}-message`;
    div.textContent = text;
    this.logEl.appendChild(div);
    if (this.expanded || isDebugMode()) {
      this.scrollToBottom();
    }
  }

  private scrollToBottom(): void {
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  private sendTextToAgent(text: string): void {
    if (!natsClient) return;
    natsClient.send({ text });
  }
}
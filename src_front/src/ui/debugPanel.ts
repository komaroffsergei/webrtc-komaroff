import type { ServerLogEntry } from "../types";
import { logger } from "../core/logging";

export class DebugPanel {
  private container: HTMLDivElement;
  private logContainer: HTMLDivElement;
  private toggleButton: HTMLButtonElement;
  private logs: ServerLogEntry[] = [];
  private renderedCount = 0;
  private static MAX_LOGS = 500;

  constructor(root: HTMLElement) {
    this.container = document.createElement("div");
    this.container.className = "debug-panel";

    const header = document.createElement("div");
    header.className = "debug-header";

    const title = document.createElement("h3");
    title.textContent = "DEBUG";

    this.toggleButton = document.createElement("button");
    this.toggleButton.className = "debug-toggle";
    this.toggleButton.textContent = "−";
    this.toggleButton.addEventListener("click", () => this.toggle());

    const clearButton = document.createElement("button");
    clearButton.className = "clear-btn";
    clearButton.textContent = "Очистить";
    clearButton.addEventListener("click", () => this.clear());

    header.append(title, this.toggleButton, clearButton);
    this.container.append(header);

    this.logContainer = document.createElement("div");
    this.logContainer.className = "debug-logs";
    this.container.append(this.logContainer);

    root.appendChild(this.container);

    logger.addListener((entry) => this.add(entry));
  }

  private add(entry: ServerLogEntry): void {
    if (!entry.service || !entry.type || !entry.message) {
      return;
    }

    this.logs.push(entry);
    if (this.logs.length > DebugPanel.MAX_LOGS) {
      this.logs = this.logs.slice(-DebugPanel.MAX_LOGS);
      this.renderedCount = 0;
      this.render(true);
      return;
    }

    this.render();
  }

  private format(entry: ServerLogEntry): string {
    const time = entry.time ? new Date(entry.time).toLocaleTimeString() : "";
    return `[${time}] [${entry.service}] [${entry.type.toUpperCase()}] ${entry.message}`;
  }

  private render(fullRefresh = false): void {
    if (fullRefresh) {
      this.logContainer.innerHTML = "";
      this.renderedCount = 0;
    }

    const nearBottom =
      this.logContainer.scrollHeight -
        this.logContainer.scrollTop -
        this.logContainer.clientHeight <
      10;

    for (let i = this.renderedCount; i < this.logs.length; i++) {
      const row = document.createElement("div");
      row.className = `debug-log-entry log-level-${this.logs[i].type}`;
      row.textContent = this.format(this.logs[i]);
      this.logContainer.append(row);
    }

    this.renderedCount = this.logs.length;
    if (nearBottom) {
      this.logContainer.scrollTop = this.logContainer.scrollHeight;
    }
  }

  private toggle(): void {
    this.container.classList.toggle("collapsed");
    this.toggleButton.textContent = this.container.classList.contains("collapsed")
      ? "+"
      : "−";
  }

  private clear(): void {
    this.logs = [];
    this.logContainer.innerHTML = "";
    this.renderedCount = 0;
  }
}

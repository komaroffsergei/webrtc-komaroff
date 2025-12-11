type WarningEntry = {
  message: string;
  uid?: string;
};

export class WarningUI {
  private container: HTMLElement;
  private hideTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(root: HTMLElement) {
    this.container = root;
  }

  show(entry: WarningEntry): void {
    this.clearTimer();
    this.container.innerHTML = "";

    const item = document.createElement("div");
    item.className = "warning-message visible";
    item.textContent = entry.message;
    if (entry.uid) {
      item.dataset.uid = entry.uid;
    }

    this.container.appendChild(item);
    this.hideTimer = setTimeout(() => this.hide(), 5000);
  }

  hide(): void {
    this.container.innerHTML = "";
    this.clearTimer();
  }

  private clearTimer(): void {
    if (this.hideTimer) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
  }
}

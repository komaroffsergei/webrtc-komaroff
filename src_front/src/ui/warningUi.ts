export class WarningUI {
  constructor(private root: HTMLElement) {}

  show(opts: { message: string }): void {
    const el = document.createElement("div");
    el.className = "warning";
    el.textContent = opts.message;

    this.root.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }
}

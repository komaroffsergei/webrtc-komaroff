export function query(selector: string): Element | null {
  return document.querySelector(selector);
}

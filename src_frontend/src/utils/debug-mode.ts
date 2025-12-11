export function isDebugMode(): boolean {
  return document.cookie.includes('debug=1');
}

export function toggleDebugMode(): void {
  const was = isDebugMode();
  document.cookie = `debug=${was ? 0 : 1}; path=/; max-age=31536000`;
  location.reload();
}
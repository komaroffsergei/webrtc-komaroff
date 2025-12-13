export function initAudioControls(): void {
  const el = document.querySelector('.audio-controls')!;
  if (!el) return;

  // Пример: можно логировать изменения
  const vadThresh = el.querySelector('#vadThresh') as HTMLInputElement;
  const vadLevel = el.querySelector('#vadLevel') as HTMLElement;
  if (vadThresh && vadLevel) {
    vadThresh.addEventListener('input', () => {
      vadLevel.textContent = `${vadThresh.value} dBFS`;
    });
  }
}
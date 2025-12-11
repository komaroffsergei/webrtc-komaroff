import {natsClient} from "../App";

export function initDebugPanel(): void {
  const panel = document.getElementById('debugPanel')!;
  const logContainer = document.createElement('div');
  logContainer.className = 'debug-logs';
  panel.appendChild(logContainer);

  if (!natsClient) return;

  natsClient.onLog((entry) => {
    const line = document.createElement('div');
    line.className = `debug-log-entry log-${entry.type}`;
    const time = new Date(entry.time).toLocaleTimeString();
    line.textContent = `[${time}] [${entry.service}] [${entry.type}] ${entry.message}`;
    logContainer.appendChild(line);
    logContainer.scrollTop = logContainer.scrollHeight;
  });
}
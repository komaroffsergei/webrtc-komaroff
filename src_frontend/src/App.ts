import { AppConfig } from './core/config';
import { NatsClient } from './core/nats-client';
import { isDebugMode } from './utils/debug-mode';
import { ChatUI } from './ui/Chat';
import { initDebugPanel } from './ui/DebugPanel';
import { initAudioControls } from './ui/AudioControls';

export let natsClient: NatsClient | null = null;

export function initApp(): void {
  const { nats: natsCfg } = AppConfig;

  natsClient = new NatsClient(natsCfg.eventsSubject, natsCfg.agentSubject);
  natsClient.connect(natsCfg.url).then(() => {
    natsClient!.onMessage((data) => {
      if (data.type === 'message' && data.name === 'message') {
        chat.addServerMessage(data.message);
      }
    });
  });

  const chat = new ChatUI();

  if (isDebugMode()) {
    document.getElementById('debugPanel')!.style.display = 'block';
    document.querySelector('.audio-controls')!.style.display = 'block';
    initDebugPanel();
    initAudioControls();
  }
}
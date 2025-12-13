export const AppConfig = {
  nats: {
    url: import.meta.env.VITE_NATS_URL || 'ws://localhost:4222',
    eventsSubject: import.meta.env.VITE_NATS_EVENTS_SUBJECT || 'nats.events.user123',
    agentSubject: import.meta.env.VITE_NATS_AGENT_SUBJECT || 'nats.agent.user123',
  },
  debug: {
    enabled: document.cookie.includes('debug=1'),
  },
};
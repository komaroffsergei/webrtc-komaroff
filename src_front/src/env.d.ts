/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_NATS_URL?: string;
  readonly VITE_NATS_EVENTS_SUBJECT?: string;
  readonly VITE_NATS_AGENT_SUBJECT?: string;
  readonly VITE_NATS_CLIENT_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

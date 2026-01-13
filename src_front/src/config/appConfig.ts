export type AppConfig = {
  signaling: {
    offerEndpoint: string;
  };
  webrtc: {
    iceServers: RTCIceServer[];
    iceCandidatePoolSize: number;
    bundlePolicy: "balanced" | "max-bundle" | "max-compat";
    rtcpMuxPolicy: "require";
    forceRelay: boolean;
    diagnostics: boolean;
    iceGatherTimeoutMs: number;
  };
  audio: {
    vad: {
      fftSize: number;
      attackSeconds: number;
      releaseSeconds: number;
    };
    input: {
      echoCancellationDefault: boolean;
      noiseSuppressionDefault: boolean;
    };
    analyser: {
      fftSizeBg: number;
      historySecondsBg: number;
      fftSizeMic: number;
      historySecondsMic: number;
    };
  };
  ui: {
    debug: boolean;
  };
  nats: {
    url: string;
    eventsSubject: string;
    agentSubject: string;
    clientName: string;
  };
};

const runtimeSettings =
  typeof window !== "undefined" && (window as any).SETTINGS
    ? ((window as any).SETTINGS as Record<string, string | undefined>)
    : {};

const rawNatsUrl =
  runtimeSettings.NATS_URL ??
  import.meta.env.VITE_NATS_URL ??
  "ws://localhost:9222";
const natsUrl =
  typeof window !== "undefined" && window.location?.protocol === "https:"
    ? rawNatsUrl.replace(/^ws:\/\//, "wss://")
    : rawNatsUrl;
const natsEventsSubject =
  runtimeSettings.NATS_EVENTS_SUBJECT ??
  import.meta.env.VITE_NATS_EVENTS_SUBJECT ??
  "nats.events.user123";
const natsAgentSubject =
  runtimeSettings.NATS_AGENT_SUBJECT ??
  import.meta.env.VITE_NATS_AGENT_SUBJECT ??
  "nats.agent.user123";
const natsClientName =
  runtimeSettings.NATS_CLIENT_NAME ??
  import.meta.env.VITE_NATS_CLIENT_NAME ??
  "src_front";

const coreOrigin =
  runtimeSettings.CORE_ORIGIN ??
  import.meta.env.VITE_CORE_ORIGIN ??
  import.meta.env.CORE_ORIGIN;
const offerEndpoint = coreOrigin
  ? `${coreOrigin.replace(/\/$/, "")}/offer`
  : "/offer";

export const appConfig: AppConfig = {
  signaling: {
    offerEndpoint,
  },
  webrtc: {
    iceServers: [{ urls: ["stun:stun.gis-master.ru:3478"] }],
    iceCandidatePoolSize: 4,
    bundlePolicy: "max-bundle",
    rtcpMuxPolicy: "require",
    forceRelay: false,
    diagnostics: true,
    iceGatherTimeoutMs: 1000,
  },
  audio: {
    vad: {
      fftSize: 2048,
      attackSeconds: 0.02,
      releaseSeconds: 0.02,
    },
    input: {
      echoCancellationDefault: true,
      noiseSuppressionDefault: true,
    },
    analyser: {
      fftSizeBg: 512,
      historySecondsBg: 3,
      fftSizeMic: 256,
      historySecondsMic: 0.5,
    },
  },
  ui: {
    debug: true,
  },
  nats: {
    url: natsUrl,
    eventsSubject: natsEventsSubject,
    agentSubject: natsAgentSubject,
    clientName: natsClientName,
  },
};

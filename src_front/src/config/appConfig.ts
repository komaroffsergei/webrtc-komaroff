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

const defaultNatsUrl = import.meta.env.DEV
  ? "ws://localhost:9222"
  : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

const natsUrl =
  (window as any)?.SETTINGS?.NATS_URL ??  defaultNatsUrl;
const natsEventsSubject = "nats.events.user123";
const natsAgentSubject = "nats.agent.user123";
const natsClientName = "src_front";

export const appConfig: AppConfig = {
  signaling: {
    offerEndpoint: "/core/offer",
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

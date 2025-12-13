export type AppConfig = {
  signaling: {
    offerEndpoint: string;
  };
  webrtc: {
    iceServers: RTCIceServer[];
    iceCandidatePoolSize: number;
    bundlePolicy: "balanced" | "max-bundle" | "max-compat";
    rtcpMuxPolicy: "require" | "negotiate";
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
    opus: {
      maxBitrate: number;
    };
    analyser: {
      fftSize: number;
      historySeconds: number;
    };
  };
  ui: {
    debug: boolean;
    canvas: {
      width: number;
      height: number;
    };
    colors: {
      grid: string;
      in: string;
      out: string;
    };
  };
  nats: {
    url: string;
    eventsSubject: string;
    agentSubject: string;
    clientName: string;
  };
};

const natsUrl = import.meta.env.VITE_NATS_URL ?? "ws://localhost:9222";
const natsEventsSubject =
  import.meta.env.VITE_NATS_EVENTS_SUBJECT ?? "nats.events.user123";
const natsAgentSubject =
  import.meta.env.VITE_NATS_AGENT_SUBJECT ?? "nats.agent.user123";
const natsClientName =
  import.meta.env.VITE_NATS_CLIENT_NAME ?? "src_front";

export const appConfig: AppConfig = {
  signaling: {
    offerEndpoint: "/offer",
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
    opus: {
      maxBitrate: 24000,
    },
    analyser: {
      fftSize: 1024,
      historySeconds: 10,
    },
  },
  ui: {
    debug: true,
    canvas: {
      width: 400,
      height: 80,
    },
    colors: {
      grid: "#ddd",
      in: "#2b8",
      out: "#82b",
    },
  },
  nats: {
    url: natsUrl,
    eventsSubject: natsEventsSubject,
    agentSubject: natsAgentSubject,
    clientName: natsClientName,
  },
};

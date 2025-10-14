// Global configuration for the WebRTC demo
// Keep only environment- or tuning-related values here
(function(){
  window.AppConfig = {
    signaling: {
      offerEndpoint: "/offer"
    },
    webrtc: {
      iceServers: [
        { urls: ["stun:stun.gis-master.ru:3478"] },
        // Uncomment and configure TURN if behind NAT with no direct connectivity
        // { urls: ["turn:turn.example.com:3478?transport=udp", "turn:turn.example.com:3478?transport=tcp"], username: "user", credential: "pass" },
      ],
      diagnostics: true
    },
    audio: {
      input: {
        echoCancellationDefault: true,
        noiseSuppressionDefault: true
      },
      opus: {
        maxBitrate: 24000 // bps
      },
      analyser: {
        fftSize: 1024,
        historySeconds: 10
      },
      vad: {
        fftSize: 2048,
        attackSeconds: 0.02,
        releaseSeconds: 0.02
      }
    },
    ui: {
      canvas: { width: 400, height: 80 },
      colors: {
        grid: "#ddd",
        in: "#2b8",
        out: "#82b"
      }
    }
  };
})();

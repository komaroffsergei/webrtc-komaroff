import type { AppConfig } from "../config/appConfig";
import { ChatUI } from "../ui/chatUi";
import { DebugPanel } from "../ui/debugPanel";
import { WarningUI } from "../ui/warningUi";
import { CommandHandler } from "../core/commandHandler";
import { FrontendNatsClient } from "../net/natsClient";
import { createPeer, negotiate } from "../core/webrtc";
import { createEnergyVAD, type VADInstance } from "../core/vad";
import {
  attachAnalyserDraw,
  createWaveDrawer,
  type CanvasConfig,
  type AnalyserConfig,
} from "../core/audioViz";
import type { ServerEvent } from "../types";
import { logEvent } from "../core/logging";

type AudioState = {
  vadEnabled: boolean;
  vadThreshold: number;
  echoCancellation: boolean;
  noiseSuppression: boolean;
};

type CanvasViz = { stop: () => void } | null;

export class AssistantApp {
  private config: AppConfig;
  private chat: ChatUI;
  private warning: WarningUI;
  private nats: FrontendNatsClient | null = null;
  private commands: CommandHandler;
  private vad: VADInstance | null = null;
  private micStream: MediaStream | null = null;
  private peer: RTCPeerConnection | null = null;
  private sender: RTCRtpSender | null = null;
  private backgroundViz: CanvasViz = null;
  private micViz: CanvasViz = null;
  private audioState: AudioState;
  private connected = false;
  private natsReconnectTimer: number | null = null;

  private elements = {
    container: document.getElementById("assistantContainer") as HTMLElement,
    chatWindow: document.querySelector(".chat-window") as HTMLElement,
    messageLog: document.getElementById("messageLog") as HTMLElement,
    textInput: document.getElementById("textInput") as HTMLInputElement,
    micButton: document.getElementById("micButton") as HTMLButtonElement,
    micWaveform: document.getElementById("micWaveform") as HTMLCanvasElement,
    waveBackground: document.getElementById("waveBackground") as HTMLCanvasElement,
    connectionStatus: document.getElementById("connectionStatus") as HTMLElement,
    remoteAudio: document.getElementById("remoteAudio") as HTMLAudioElement,
    vadEnable: document.getElementById("vadEnable") as HTMLInputElement,
    vadThresh: document.getElementById("vadThresh") as HTMLInputElement,
    vadLevel: document.getElementById("vadLevel") as HTMLElement,
    ecEnable: document.getElementById("ecEnable") as HTMLInputElement,
    nsEnable: document.getElementById("nsEnable") as HTMLInputElement,
  };

  constructor(config: AppConfig) {
    this.config = config;
    if (!this.elements.messageLog) {
      throw new Error("messageLog element not found");
    }
    this.chat = new ChatUI(this.elements.messageLog);

    const debugRoot =
      document.getElementById("debugPanelRoot") ?? document.body;
    new DebugPanel(debugRoot);

    const warningRoot =
      document.getElementById("warningContainer") ?? document.body;
    this.warning = new WarningUI(warningRoot);

    this.audioState = {
      vadEnabled: this.elements.vadEnable?.checked ?? true,
      vadThreshold: this.elements.vadThresh?.valueAsNumber ?? -55,
      echoCancellation: this.elements.ecEnable?.checked ?? true,
      noiseSuppression: this.elements.nsEnable?.checked ?? true,
    };

    this.commands = new CommandHandler();
    this.registerBuiltinCommands();

    this.registerUIEvents();
    this.initAudioControls();
    this.chat.addMessage("Голосовой ассистент готов к работе", "status");
  }

  start(): void {
    this.connectNats();
  }

  private registerUIEvents(): void {
    this.elements.micButton?.addEventListener("click", () => this.toggleConnection());
    this.elements.textInput?.addEventListener("keypress", (event) =>
      this.handleTextInput(event),
    );

    window.addEventListener("resize", () => {
      if (this.connected) {
        this.setupCanvasSizes();
        if (this.micStream) {
          this.setupBackgroundWaveform(this.micStream);
        }
      }
    });
  }

  private registerBuiltinCommands(): void {
    this.commands.register("alert", (params) => {
      const msg =
        typeof params === "object" && params
          ? (params as Record<string, unknown>).msg
          : params;
      window.alert(String(msg ?? "Alert from server"));
    });

    this.commands.register("console", (params) => {
      logEvent({
        service: "command",
        type: "info",
        message: JSON.stringify(params),
      });
    });

    this.commands.register("reload", () => window.location.reload());

    this.commands.register("redirect", (params) => {
      const url =
        typeof params === "object" && params
          ? (params as Record<string, unknown>).url
          : params;
      if (typeof url === "string") {
        window.location.href = url;
      }
    });
  }

  private initAudioControls(): void {
    const updateVadLevel = () => {
      if (this.elements.vadLevel) {
        this.elements.vadLevel.textContent = `${this.audioState.vadThreshold} dBFS`;
      }
    };

    this.elements.vadEnable?.addEventListener("change", (event) => {
      this.audioState.vadEnabled = (event.target as HTMLInputElement).checked;
      if (!this.audioState.vadEnabled) {
        this.stopVAD();
        if (this.sender && this.micStream) {
          const track = this.micStream.getAudioTracks()[0];
          this.sender.replaceTrack(track).catch(() => undefined);
        }
      } else if (this.micStream) {
        this.applyVAD(this.micStream.getAudioTracks()[0]);
      }
    });

    this.elements.vadThresh?.addEventListener("input", (event) => {
      this.audioState.vadThreshold = (event.target as HTMLInputElement).valueAsNumber;
      updateVadLevel();
    });

    this.elements.ecEnable?.addEventListener("change", (event) => {
      this.audioState.echoCancellation = (event.target as HTMLInputElement).checked;
      if (this.connected) {
        this.reconfigureMicrophone();
      }
    });

    this.elements.nsEnable?.addEventListener("change", (event) => {
      this.audioState.noiseSuppression = (event.target as HTMLInputElement).checked;
      if (this.connected) {
        this.reconfigureMicrophone();
      }
    });

    updateVadLevel();
  }

  private async handleTextInput(event: KeyboardEvent): Promise<void> {
    if (event.key !== "Enter") return;
    const target = event.target as HTMLInputElement;
    const text = target.value.trim();
    if (!text) return;
    target.value = "";
    this.chat.addMessage(text, "user");
    try {
      await this.commands.sendMessage(text);
    } catch (err) {
      this.chat.addMessage("Ошибка отправки сообщения", "status");
      console.error(err);
    }
  }

  private async toggleConnection(): Promise<void> {
    if (this.connected) {
      this.disconnect();
    } else {
      await this.connect();
    }
  }

  private getUserMediaConstraints(): MediaTrackConstraints {
    return {
      echoCancellation: this.audioState.echoCancellation,
      noiseSuppression: this.audioState.noiseSuppression,
      autoGainControl: true,
      channelCount: 1,
      sampleRate: 48000,
    };
  }

  private async reconfigureMicrophone(): Promise<void> {
    if (!this.peer) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: this.getUserMediaConstraints(),
        video: false,
      });
      const track = stream.getAudioTracks()[0];
      const sender = this.peer
        .getSenders()
        .find((s) => s.track?.kind === "audio");
      if (sender && track) {
        await sender.replaceTrack(track);
        this.sender = sender;
      }
      this.stopMic();
      this.micStream = stream;
      this.setupBackgroundWaveform(stream);
    } catch (err) {
      console.warn("Failed to reconfigure microphone", err);
    }
  }

  private async connect(): Promise<void> {
    try {
      this.updateStatus("Подключение...");
      this.chat.addMessage("Подключение...", "status");
      this.expandChat();

      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: this.getUserMediaConstraints(),
        video: false,
      });
      this.setupCanvasSizes();
      this.setupBackgroundWaveform(this.micStream);
      this.setupMicWaveform(this.micStream);

      this.peer = await createPeer(this.config);
      const track = this.micStream.getAudioTracks()[0];
      this.sender = this.peer.addTrack(track, this.micStream);

      if (this.audioState.vadEnabled) {
        this.applyVAD(track);
      }

      this.peer.ontrack = (event) => {
        const stream = event.streams[0] ?? new MediaStream([event.track]);
        if (this.elements.remoteAudio) {
          this.elements.remoteAudio.srcObject = stream;
          this.elements.remoteAudio.muted = false;
          this.elements.remoteAudio
            .play()
            .catch((err) => console.warn("play rejected", err));
        }
      };

      await negotiate(this.peer, this.config);
      this.connected = true;
      this.elements.micButton?.classList.add("expanded");
      this.updateStatus("Подключено");
      this.chat.addMessage("Соединение установлено", "server");
    } catch (err) {
      console.error("Connection failed", err);
      this.updateStatus("Ошибка подключения");
      this.chat.addMessage("Ошибка подключения", "status");
      this.disconnect();
    }
  }

  private disconnect(): void {
    this.connected = false;
    this.elements.micButton?.classList.remove("expanded");
    this.collapseChat();
    this.updateStatus("Отключено");
    this.chat.addMessage("Соединение разорвано", "status");

    this.stopVAD();
    this.stopMic();

    if (this.peer) {
      try {
        this.peer.getSenders().forEach((sender) => {
          try {
            sender.replaceTrack(null);
            sender.track?.stop();
          } catch {
            /* ignore */
          }
        });
      } catch {
        /* ignore */
      }
      this.peer.close();
      this.peer = null;
    }

    this.sender = null;
    this.stopViz();
  }

  private stopMic(): void {
    try {
      this.micStream?.getTracks().forEach((track) => track.stop());
    } catch {
      /* ignore */
    }
    this.micStream = null;
  }

  private stopViz(): void {
    this.backgroundViz?.stop();
    this.backgroundViz = null;
    this.micViz?.stop();
    this.micViz = null;
  }

  private stopVAD(): void {
    this.vad?.cleanup();
    this.vad = null;
  }

  private applyVAD(track: MediaStreamTrack): void {
    if (!this.sender) return;
    this.stopVAD();
    this.vad = createEnergyVAD(
      track,
      this.config,
      () => this.audioState.vadThreshold,
      (value) => {
        if (this.elements.vadLevel) {
          this.elements.vadLevel.textContent = `${value} dBFS`;
        }
      },
    );
    this.sender.replaceTrack(this.vad.track).catch((err) => {
      console.warn("replaceTrack failed", err);
    });
  }

  private expandChat(): void {
    this.elements.chatWindow?.classList.add("expanded");
    setTimeout(() => this.setupCanvasSizes(), 100);
  }

  private collapseChat(): void {
    this.elements.chatWindow?.classList.remove("expanded");
  }

  private setupCanvasSizes(): void {
    const canvas = this.elements.waveBackground;
    const container = this.elements.chatWindow;
    if (canvas && container) {
      const rect = container.getBoundingClientRect();
      canvas.width = rect.width + 20;
      canvas.height = rect.height + 20;
    }
    if (this.elements.micWaveform) {
      this.elements.micWaveform.width = 140;
      this.elements.micWaveform.height = 40;
    }
  }

  private setupBackgroundWaveform(stream: MediaStream): void {
    if (!this.elements.waveBackground) return;
    const ctx = this.elements.waveBackground.getContext("2d");
    if (!ctx) return;
    this.backgroundViz?.stop();

    const canvasConfig: CanvasConfig = {
      width: this.elements.waveBackground.width,
      height: this.elements.waveBackground.height,
      gridColor: "transparent",
    };
    const analyserConfig: AnalyserConfig = {
      fftSize: 512,
      historySeconds: 3,
    };

    const drawer = createWaveDrawer(ctx, canvasConfig);
    const audioContext = new (window.AudioContext ||
      (window as any).webkitAudioContext)();
    this.backgroundViz = attachAnalyserDraw(
      audioContext,
      stream,
      analyserConfig,
      (history) => drawer(history, "#007aff"),
    );
  }

  private setupMicWaveform(stream: MediaStream): void {
    if (!this.elements.micWaveform) return;
    const ctx = this.elements.micWaveform.getContext("2d");
    if (!ctx) return;
    this.micViz?.stop();

    const canvasConfig: CanvasConfig = {
      width: this.elements.micWaveform.width,
      height: this.elements.micWaveform.height,
      gridColor: "transparent",
    };
    const analyserConfig: AnalyserConfig = {
      fftSize: 256,
      historySeconds: 0.5,
    };

    const drawer = createWaveDrawer(ctx, canvasConfig);
    const audioContext = new (window.AudioContext ||
      (window as any).webkitAudioContext)();
    this.micViz = attachAnalyserDraw(
      audioContext,
      stream,
      analyserConfig,
      (history) => drawer(history, "#fff"),
    );
  }

  private updateStatus(text: string): void {
    if (this.elements.connectionStatus) {
      this.elements.connectionStatus.textContent = text;
    }
  }

  private async handleServerEvent(event: ServerEvent): Promise<void> {
    if (!event) return;
    if (event.service && event.type && event.message) {
      logEvent({
        service: event.service,
        type: event.type,
        message: event.message,
        time: event.time,
      });
    }

    const eventName = (event as { name?: string }).name;
    if (eventName === "message" && typeof event.message === "string") {
      this.chat.addMessage(event.message, "server");
    }

    if (eventName === "model_downloading_status") {
      if (event.type === "info") {
        if (event.message === "downloading") {
          this.updateStatus("Скачивание модели");
        } else if (event.message === "exists") {
          this.updateStatus("Модель готова");
        }
      } else if (event.type === "error") {
        this.warning.show({ message: event.message });
      }
    }

    if (eventName === "model_downloading_percent") {
      const percent = (event as { message?: number }).message ?? 0;
      this.updateStatus(`Скачивание модели ${percent}%`);
    }

    await this.commands.handleServerEvent(event);
  }

  private async connectNats(): Promise<void> {
    if (!this.nats) {
      this.nats = new FrontendNatsClient();
      this.nats.onStatus((status) => {
        if (status.type === "connected") {
          this.updateStatus("События подключены");
          return;
        }
        if (status.type === "error") {
          logEvent({
            service: "nats",
            type: "error",
            message: `NATS error: ${status.error.message ?? String(status.error)}`,
          });
          this.updateStatus("NATS: ошибка, переподключение...");
          this.scheduleNatsReconnect();
          return;
        }
        if (status.type === "closed") {
          this.updateStatus("NATS: отключено, переподключение...");
          this.scheduleNatsReconnect();
        }
      });
    }
    try {
      const connected = await this.nats.connect({
        url: this.config.nats.url,
        name: this.config.nats.clientName,
      });
      if (connected) {
        await this.nats.subscribe(this.config.nats.eventsSubject, (payload) =>
          this.handleNatsPayload(payload),
        );
      }
    } catch (err) {
      logEvent({
        service: "nats",
        type: "error",
        message: `Connect failed: ${String(err)}`,
      });
      this.updateStatus("Ошибка подключения к событиям, повтор...");
      this.scheduleNatsReconnect();
    }
  }

  private scheduleNatsReconnect(): void {
    if (this.natsReconnectTimer !== null) {
      return;
    }
    this.natsReconnectTimer = window.setTimeout(() => {
      this.natsReconnectTimer = null;
      this.connectNats().catch(() => undefined);
    }, 3000);
  }

  private handleNatsPayload(raw: string): void {
    try {
      const evt = JSON.parse(raw) as ServerEvent;
      void this.handleServerEvent(evt);
    } catch (err) {
      logEvent({
        service: "nats",
        type: "error",
        message: `Invalid event payload: ${String(err)}`,
      });
    }
  }
}

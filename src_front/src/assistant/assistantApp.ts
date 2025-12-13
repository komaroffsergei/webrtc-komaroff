import type { AppConfig } from "../config/appConfig";
import { ChatUI } from "../ui/chatUi";
import { DebugPanel } from "../ui/debugPanel";
import { WarningUI } from "../ui/warningUi";
import { CommandHandler } from "../core/commandHandler";
import { FrontendNatsClient } from "../net/natsClient";
import { createPeer, negotiate } from "../core/webrtc";
import type { ServerEvent } from "../types";
import { logEvent } from "../core/logging";
import { getAssistantElements } from "../ui/elements";
import { AudioVizController } from "../ui/audioVizController";
import { VADController } from "../core/vadController";

type AudioState = {
  vadEnabled: boolean;
  vadThreshold: number;
  echoCancellation: boolean;
  noiseSuppression: boolean;
};

export class AssistantApp {
  private config: AppConfig;
  private chat: ChatUI;
  private warning: WarningUI;
  private nats: FrontendNatsClient | null = null;
  private commands: CommandHandler;

  private micStream: MediaStream | null = null;
  private peer: RTCPeerConnection | null = null;
  private sender: RTCRtpSender | null = null;

  private audioState: AudioState;
  private connected = false;
  private natsReconnectTimer: number | null = null;

  private elements = getAssistantElements();
  private viz: AudioVizController;
  private vadCtl: VADController;

  constructor(config: AppConfig) {
    this.config = config;

    if (!this.elements.messageLog) {
      throw new Error("messageLog element not found");
    }
    this.chat = new ChatUI(this.elements.messageLog);

    const debugRoot = document.getElementById("debugPanelRoot") ?? document.body;
    if (this.config.ui.debug) {
      new DebugPanel(debugRoot);
    }

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

    this.viz = new AudioVizController(this.elements);
    this.vadCtl = new VADController(this.config);

    this.registerUIEvents();
    this.initAudioControls();
    this.chat.addMessage("Голосовой ассистент готов к работе", "status");
  }

  start(): void {
    this.connectNats();
  }

  private registerUIEvents(): void {
    this.elements.micButton?.addEventListener("click", () =>
      this.toggleConnection(),
    );

    this.elements.textInput?.addEventListener("keypress", (event) =>
      this.handleTextInput(event),
    );

    window.addEventListener("resize", () => {
      if (!this.connected) return;
      this.viz.setupCanvasSizes();
      if (this.micStream) {
        this.viz.attach(this.micStream);
      }
    });
  }

  private registerBuiltinCommands(): void {
    this.commands.register("alert", (params) => {
      const msg =
        typeof params === "object" && params
          ? (params as Record<string, unknown>).msg
          : params;
      window.alert(String(msg ?? ""));
    });

    this.commands.register("warning", (params, uid) => {
      const msg =
        typeof params === "object" && params
          ? (params as Record<string, unknown>).msg
          : params;
      this.warning.show({ message: String(msg ?? "Warning"), uid });
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
    this.elements.vadEnable?.addEventListener("change", () => {
      this.audioState.vadEnabled = this.elements.vadEnable?.checked ?? true;
      if (this.connected && this.micStream) {
        const track = this.micStream.getAudioTracks()[0];
        if (track && this.sender) {
          this.applyVAD(track);
        }
      }
    });

    this.elements.vadThresh?.addEventListener("input", () => {
      this.audioState.vadThreshold = this.elements.vadThresh?.valueAsNumber ?? -55;
      if (this.elements.vadLevel) {
        this.elements.vadLevel.textContent = `${this.audioState.vadThreshold} dBFS`;
      }
    });

    this.elements.ecEnable?.addEventListener("change", () => {
      this.audioState.echoCancellation = this.elements.ecEnable?.checked ?? true;
    });

    this.elements.nsEnable?.addEventListener("change", () => {
      this.audioState.noiseSuppression = this.elements.nsEnable?.checked ?? true;
    });
  }

  private handleTextInput(event: KeyboardEvent): void {
    if (event.key !== "Enter") return;

    const input = this.elements.textInput;
    const text = input?.value?.trim();
    if (!text) return;

    this.chat.addMessage(text, "user");
    input.value = "";

    this.commands
      .sendMessage(text)
      .then(() => undefined)
      .catch((err) => {
        this.chat.addMessage(`Ошибка отправки: ${String(err)}`, "status");
      });
  }

  private toggleConnection(): void {
    if (this.connected) {
      this.disconnect();
      return;
    }
    this.connect().catch((err) => {
      this.chat.addMessage(`Ошибка подключения: ${String(err)}`, "status");
      this.updateStatus("Ошибка подключения");
      this.disconnect();
    });
  }

  private async connect(): Promise<void> {
    this.updateStatus("Подключение...");

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: this.audioState.echoCancellation,
        noiseSuppression: this.audioState.noiseSuppression,
      },
      video: false,
    });

    this.micStream = stream;

    this.peer = await createPeer(this.config);

    // локальный трек в RTCPeerConnection
    const track = stream.getAudioTracks()[0];
    if (!track) {
      throw new Error("No audio track in mic stream");
    }

    this.sender = this.peer.addTrack(track, stream);

    // VAD, если включен
    this.applyVAD(track);

    // ontrack: удаленный звук
    this.peer.ontrack = (ev) => {
      const remoteStream = ev.streams?.[0];
      if (remoteStream && this.elements.remoteAudio) {
        this.elements.remoteAudio.srcObject = remoteStream;
      }
    };

    await negotiate(this.peer, this.config);

    this.connected = true;
    this.elements.micButton?.classList.add("expanded");
    this.expandChat();
    this.updateStatus("Подключено");
    this.chat.addMessage("Соединение установлено", "status");

    this.viz.setupCanvasSizes();
    this.viz.attach(stream);
  }

  private disconnect(): void {
    this.connected = false;

    this.elements.micButton?.classList.remove("expanded");
    this.collapseChat();
    this.updateStatus("Отключено");
    this.chat.addMessage("Соединение разорвано", "status");

    this.vadCtl.stop();
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
    this.viz.stop();
  }

  private stopMic(): void {
    try {
      this.micStream?.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    this.micStream = null;
  }

  private applyVAD(track: MediaStreamTrack): void {
    if (!this.sender) return;

    if (!this.audioState.vadEnabled) {
      // VAD выключен: возвращаем оригинальный трек
      this.vadCtl.stop();
      this.sender.replaceTrack(track).catch((err) => {
        console.warn("replaceTrack failed", err);
      });
      return;
    }

    this.vadCtl.apply(
      track,
      this.sender,
      () => this.audioState.vadThreshold,
      (value) => {
        if (this.elements.vadLevel) {
          this.elements.vadLevel.textContent = `${value} dBFS`;
        }
      },
    );
  }

  private expandChat(): void {
    this.elements.chatWindow?.classList.add("expanded");
    setTimeout(() => this.viz.setupCanvasSizes(), 100);
  }

  private collapseChat(): void {
    this.elements.chatWindow?.classList.remove("expanded");
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
          this.updateStatus("Скачивание модели...");
        }
        if (event.message === "ready") {
          this.updateStatus("Модель готова");
        }
      }
      if (event.type === "error") {
        this.updateStatus("Ошибка модели");
      }
    }

    if (eventName === "model_downloading_percent") {
      const percent = typeof event.message === "number" ? event.message : 0;
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
          this.updateStatus("NATS: ошибка, переподключение.");
          this.scheduleNatsReconnect();
          return;
        }

        if (status.type === "closed") {
          this.updateStatus("NATS: отключено, переподключение.");
          this.scheduleNatsReconnect();
        }
      });
    }

    try {
      const ok = await this.nats.connect({
        url: this.config.nats.url,
        name: this.config.nats.clientName,
      });

      if (ok) {
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
      this.updateStatus("Ошибка подключения к событиям, повтор.");
      this.scheduleNatsReconnect();
    }
  }

  private scheduleNatsReconnect(): void {
    if (this.natsReconnectTimer !== null) return;

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

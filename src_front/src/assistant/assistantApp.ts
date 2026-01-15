import type { AppConfig } from "../config/appConfig";
import { getAssistantElements } from "../ui/elements";
import { ChatUI } from "../ui/chatUi";
import { WarningUI } from "../ui/warningUi";
import { setStatus } from "../ui/status";
import { bindMicButton } from "../ui/micButton";
import { createAudioState } from "../audio/audioState";
import {
  connectSession,
  disconnectSession,
  isConnected,
} from "../webrtc/session";
import { FrontendNatsClient } from "../net/natsClient";
import { CommandHandler } from "../core/commandHandler";
import { logError, logEvent } from "../core/logging";
import { AgentCommandHandler } from "../agentCommands/agentCommandHandler";
import {AgentMessage, ServerEvent} from "../types";

/* ===========================
   AssistantApp
   =========================== */
export class AssistantApp {
  private el = getAssistantElements();

  private chat: ChatUI;
  private warning: WarningUI;

  private audio = createAudioState(this.el, this.config);
  private commands = new CommandHandler();

  private nats = new FrontendNatsClient();
  private natsReconnectTimer: number | null = null;

  private pendingThinkingId: string | null = null;
  private agentCommands: AgentCommandHandler;

  constructor(private config: AppConfig) {
    /* ---------- CHAT ---------- */
    if (!this.el.messageLog) throw new Error("messageLog element not found");
    this.chat = new ChatUI(this.el.messageLog, this.el.textInput);

    /* ---------- WARNING ---------- */
    const warningRoot =
      document.getElementById("warningContainer") ??
      document.body.appendChild(document.createElement("div"));
    this.warning = new WarningUI(warningRoot);

    this.agentCommands = new AgentCommandHandler({
      chat: this.chat,
      warning: this.warning,
    });

    /* ---------- UI bindings ---------- */
    bindMicButton(this.el, () => this.toggleConnection());
    this.bindTextInput();

    this.registerBuiltinCommands();

    this.chat.addMessage("Голосовой ассистент готов к работе", "status");
    this.chat.addMessage("Покажи аэропорты в радиусе 100км", "user");
  }

  /* ===========================
     PUBLIC
     =========================== */

  start(): void {
    void this.connectNats();
  }

  /* ===========================
     UI
     =========================== */

  private bindTextInput(): void {
    this.el.textInput?.addEventListener("keypress", (e) => {
      if (e.key !== "Enter") return;

      const text = this.el.textInput!.value.trim();
      if (!text) return;

      this.el.textInput!.value = "";
      this.chat.addMessage(text, "user");

      // Показать "агент думает" сразу после отправки
      this.chat.removeThinking(this.pendingThinkingId);
      this.pendingThinkingId = this.chat.addThinking();

      void this.commands.sendMessage(text).catch((err) => {
        this.chat.removeThinking(this.pendingThinkingId);
        this.pendingThinkingId = null;
        this.warning.show({ message: String(err) });
      });
    });
  }

  /* ===========================
     CONNECTION
     =========================== */

  private async toggleConnection(): Promise<void> {
    if (isConnected()) {
      disconnectSession();
      setStatus(this.el, "Отключено");
      this.chat.addMessage("Отключено", "status");
      return;
    }

    try {
      await connectSession(this.config, this.el, this.audio, (t) => {
        if (this.el.vadLevel) this.el.vadLevel.textContent = t;
      });

      setStatus(this.el, "Подключено");
      // this.chat.addMessage("Подключено", "status");
    } catch (err) {
      this.warning.show({ message: `Connect failed: ${String(err)}` });
      setStatus(this.el, "Ошибка подключения");
      logError("webrtc", err);
    }
  }

  /* ===========================
     COMMANDS
     =========================== */

  private registerBuiltinCommands(): void {
    this.commands.register("alert", (params) => {
      const msg = typeof params === "string" ? params : JSON.stringify(params);
      this.warning.show({ message: msg });
    });
  }

  /* ===========================
     NATS
     =========================== */

  private async connectNats(): Promise<void> {
    this.nats.onStatus((s) => {
      if (s.type === "connected") {
        setStatus(this.el, "События подключены");
      }

      if (s.type === "closed") {
        setStatus(this.el, "NATS отключено, переподключение…");
        this.scheduleNatsReconnect();
      }

      if (s.type === "error") {
        logError("nats", s.error);
        setStatus(this.el, "NATS: ошибка, переподключение…");
        this.scheduleNatsReconnect();
      }
    });

    try {
      await this.nats.connect({
        url: this.config.nats.url,
        name: this.config.nats.clientName,
      });

      await this.nats.subscribe(this.config.nats.eventsSubject, (payload) =>
        this.handleNatsPayload(payload),
      );
    } catch (err) {
      logError("nats", err);
      setStatus(this.el, "Ошибка подключения к событиям");
      this.scheduleNatsReconnect();
    }
  }

  private scheduleNatsReconnect(): void {
    if (this.natsReconnectTimer !== null) return;

    this.natsReconnectTimer = window.setTimeout(() => {
      this.natsReconnectTimer = null;
      void this.connectNats();
    }, 3000);
  }

  private handleNatsPayload(payload: string): void {
    try {
      const event = JSON.parse(payload) as ServerEvent;
      void this.handleServerEvent(event);
    } catch (err) {
      logError("nats", err);
    }
  }

  private async handleServerEvent(event: ServerEvent): Promise<void> {
    // logs
    logEvent(event);

    // Обычное сообщение (старый формат)
    // if (
    //   (event as any).name === "message" &&
    //   typeof (event as any).message === "string"
    // ) {
    //   this.chat.removeThinking(this.pendingThinkingId);
    //   this.pendingThinkingId = null;
    //   this.chat.addMessage((event as any).message, "server");
    //   return;
    // }

    if (event.kind === "message") {
      if ((event.message as AgentMessage)?.client_handler) {
        this.chat.removeThinking(this.pendingThinkingId);
        this.pendingThinkingId = null;
        this.agentCommands.handle(event.message as AgentMessage);
        return;
      } else if(event.message && typeof event.message === 'string') {
        this.chat.addMessage(event.message, "server");
        return;
      }
    }

    // await this.commands.handleServerEvent(event);
  }
}

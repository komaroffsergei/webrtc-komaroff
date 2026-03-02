import type {AppConfig} from "../config/appConfig";
import {getAssistantElements} from "../ui/elements";
import {ChatUI} from "../ui/chatUi";
import {WarningUI} from "../ui/warningUi";
import {setModelStatus, setStatus} from "../ui/status";
import {bindMicButton} from "../ui/micButton";
import {createAudioState} from "../audio/audioState";
import {
  connectSession,
  disconnectSession,
  isConnected,
  setMicEnabled,
} from "../webrtc/session";
import {FrontendNatsClient} from "../net/natsClient";
import {CommandHandler} from "../core/commandHandler";
import {logError, logEvent} from "../core/logging";
import {AgentCommandHandler} from "../agentCommands/agentCommandHandler";
import {ClientHandlerCommand, HistoryTurn, ServerEvent} from "../types";
import { MapController } from "../map/mapController";

/* ===========================
   AssistantApp
   =========================== */
export class AssistantApp {
  private static readonly SESSION_STORAGE_KEY = "assistant.session_id";

  private el = getAssistantElements();

  private chat: ChatUI;
  private warning: WarningUI;
  private map = new MapController();

  private audio = createAudioState(this.el, this.config);
  private commands = new CommandHandler();

  private nats = new FrontendNatsClient();
  private natsReconnectTimer: number | null = null;

  private agentCommands: AgentCommandHandler;
  private modelStatuses = new Map<string, {status: string; percent?: number}>();

  constructor(private config: AppConfig) {
    this.map.init("mapRoot");
    /* ---------- CHAT ---------- */
    if (!this.el.messageLog) throw new Error("messageLog element not found");
    this.chat = new ChatUI(
      this.el.messageLog,
      this.el.textInput,
      this.el.micButton,
    );
    this.chat.setEditHandler((turnId, text) => this.handleEdit(turnId, text));

    /* ---------- WARNING ---------- */
    const warningRoot =
      document.getElementById("warningContainer") ??
      document.body.appendChild(document.createElement("div"));
    this.warning = new WarningUI(warningRoot);

    this.agentCommands = new AgentCommandHandler({
      chat: this.chat,
      warning: this.warning,
      map: this.map,
    });

    /* ---------- UI bindings ---------- */
    bindMicButton(this.el, () => this.toggleConnection());
    this.bindTextInput();

    this.registerBuiltinCommands();

    this.chat.addMessage("Голосовой ассистент готов к работе", "status");
  }

  /* ===========================
     PUBLIC
     =========================== */

  start(): void {
    this.restoreSessionIdFromStorage();
    void this.restoreChatHistory();
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
      const turnId = crypto.randomUUID();
      this.chat.addMessage(text, "user", { turnId, editable: true });

      this.chat.clearThinking();
      this.chat.setThinking("Thinking…");

      void this.commands.sendMessage(text, turnId).then((sessionId) => {
        this.persistSessionId(sessionId);
      }).catch((err) => {
        this.chat.clearThinking();
        this.warning.show({message: String(err)});
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
      const sessionId = await connectSession(this.config, this.el, this.audio, (t) => {
        if (this.el.vadLevel) this.el.vadLevel.textContent = t;
      }, { sessionId: this.commands.getSessionId() });
      if (sessionId) {
        this.commands.setSessionId(sessionId);
        this.persistSessionId(sessionId);
      }

      setStatus(this.el, "Подключено");
      // this.chat.addMessage("Подключено", "status");
    } catch (err) {
      this.warning.show({message: `Connect failed: ${String(err)}`});
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
      this.warning.show({message: msg});
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
        user: this.config.nats.user,
        pass: this.config.nats.pass,
        token: this.config.nats.token,
      });

      await this.nats.subscribe(this.config.nats.eventsSubject, (payload) =>
        this.handleNatsPayload(payload),
      );
      void this.requestInitMap();
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

  private async requestInitMap(): Promise<void> {
    try {
      const resp = await fetch("/core/init_map", {method: "POST"});
      if (!resp.ok) logError("core", new Error(`init_map failed: ${resp.status}`));
    } catch (err) {
      logError("core", err);
    }
  }

  private async handleServerEvent(event: ServerEvent): Promise<void> {
    logEvent(event);

    if (event.type === "log") {
      const txt = typeof event.data.text === "string" ? event.data.text : null;
      if (event.kind === "error" && txt) {
        // this.chat.addMessage(txt, "status");
      }
      return;
    }

    if (event.type !== "command") {
      console.warn("[nats] Unknown event type", event.type, event);
      return;
    }

    switch (event.kind) {
      case "message": {
        const text = typeof event.data.text === "string" ? event.data.text : null;
        if (!text) {
          console.warn("[nats] Invalid message payload", event);
          return;
        }
        this.chat.finishThinking();
        this.chat.addMessage(text, "server");
        return;
      }
      case "transcription": {
        const text = typeof event.data.text === "string" ? event.data.text : null;
        const turnId = typeof event.data.turn_id === "string" ? event.data.turn_id : crypto.randomUUID();
        if (!text) {
          console.warn("[nats] Invalid transcription payload", event);
          return;
        }
        this.chat.clearThinking();
        this.chat.addMessage(text, "user", { turnId, editable: true });
        this.chat.setThinking("Thinking…");
        return;
      }
      case "thought": {
        const summary = typeof event.data.summary === "string" ? event.data.summary : "Thinking…";
        const content = typeof event.data.content === "string" ? event.data.content : undefined;
        const scenario = this.readScenario(event.data.scenario);
        const tools = this.readTools(event.data.tools);
        this.chat.updateThinking(summary, content, {scenario, tools});
        return;
      }
      case "status_vad":
      case "status_asr":
      case "status_llm": {
        const status = typeof event.data.status === "string" ? event.data.status : null;
        const percent = typeof event.data.percent === "number" ? event.data.percent : undefined;
        if (!status) {
          console.warn("[nats] Invalid status payload", event);
          return;
        }
        this.updateModelStatus(event.kind, status, percent);
        return;
      }
      case "voice": {
        const blocked = event.data.blocked;
        if (typeof blocked !== "boolean") {
          console.warn("[nats] Invalid voice payload", event);
          return;
        }
        this.chat.setVoiceBlocked(blocked);
        setMicEnabled(!blocked);
        if (this.el.micWaveform) this.el.micWaveform.style.display = blocked ? "none" : "";
        if (this.el.waveBackground) this.el.waveBackground.style.display = blocked ? "none" : "";
        return;
      }
      case "client": {
        const command = typeof event.data.command === "string" ? event.data.command : null;
        if (!command) {
          console.warn("[nats] Invalid client payload", event);
          return;
        }
        const artifacts = this.readArtifacts(event.data.artifacts);
        const payload: ClientHandlerCommand = artifacts ? {command, artifacts} : {command};
        this.chat.finishThinking();
        this.agentCommands.handle(payload);
        return;
      }
      default:
        console.warn("[nats] Unknown command kind", event.kind, event);
    }
  }

  private updateModelStatus(kind: string, status: string, percent?: number): void {
    const clippedPercent =
      typeof percent === "number" ? Math.max(0, Math.min(100, Math.round(percent))) : undefined;
    this.modelStatuses.set(kind, {status, percent: clippedPercent});

    const label = (k: string): string => {
      if (k === "status_vad") return "VAD";
      if (k === "status_asr") return "ASR";
      if (k === "status_llm") return "LLM";
      return k;
    };

    const fmt = (k: string, v: {status: string; percent?: number}): string => {
      if (v.status === "downloading" && typeof v.percent === "number") return `${label(k)}: downloading ${v.percent}%`;
      return `${label(k)}: ${v.status}`;
    };

    const text = Array.from(this.modelStatuses.entries())
      .map(([k, v]) => fmt(k, v))
      .join(" | ");
    setModelStatus(this.el, text);
  }

  private readArtifacts(raw: unknown): ClientHandlerCommand["artifacts"] | undefined {
    if (!raw || typeof raw !== "object") return undefined;
    const rec = raw as Record<string, unknown>;
    const all = Array.isArray(rec.all) ? rec.all.filter((x) => typeof x === "string") : [];
    const last = typeof rec.last === "string" ? rec.last : null;
    const payload = rec.payload && typeof rec.payload === "object" ? (rec.payload as Record<string, unknown>) : {};
    if (!all.length && !last && !Object.keys(payload).length) return undefined;
    return {all, last, payload};
  }

  private readScenario(raw: unknown): { id: string; reason?: string } | undefined {
    if (!raw || typeof raw !== "object") return undefined;
    const rec = raw as Record<string, unknown>;
    const id = typeof rec.id === "string" ? rec.id : null;
    if (!id) return undefined;
    const reason = typeof rec.reason === "string" ? rec.reason : undefined;
    return reason ? {id, reason} : {id};
  }

  private readTools(raw: unknown): string[] | undefined {
    if (!Array.isArray(raw)) return undefined;
    const tools = raw.filter((x) => typeof x === "string");
    return tools.length ? tools : undefined;
  }

  private async handleEdit(turnId: string, text: string): Promise<void> {
    const ok = this.chat.rewriteFromUserTurn(turnId, text);
    if (!ok) {
      this.warning.show({message: "Не удалось найти сообщение для редактирования"});
      return;
    }
    this.chat.setThinking("Thinking…");
    try {
      const sessionId = await this.commands.sendEditedMessage(text, turnId);
      this.persistSessionId(sessionId);
    } catch (err) {
      this.chat.clearThinking();
      this.warning.show({message: `Edit failed: ${String(err)}`});
    }
  }

  private restoreSessionIdFromStorage(): void {
    const sid = sessionStorage.getItem(AssistantApp.SESSION_STORAGE_KEY);
    if (sid && typeof sid === "string") {
      this.commands.setSessionId(sid);
    }
  }

  private persistSessionId(sessionId: string | null): void {
    if (!sessionId) return;
    this.commands.setSessionId(sessionId);
    sessionStorage.setItem(AssistantApp.SESSION_STORAGE_KEY, sessionId);
  }

  private async restoreChatHistory(): Promise<void> {
    const sid = this.commands.getSessionId();
    if (!sid) return;
    try {
      const qs = new URLSearchParams({ session_id: sid, limit: "200" });
      const resp = await fetch(`/core/history?${qs.toString()}`);
      if (!resp.ok) {
        throw new Error(`History request failed: ${resp.status}`);
      }
      const data = (await resp.json()) as { ok?: unknown; items?: unknown };
      if (data.ok !== true || !Array.isArray(data.items)) return;
      const turns = data.items.filter((x): x is HistoryTurn => {
        if (!x || typeof x !== "object") return false;
        const rec = x as Record<string, unknown>;
        return (
          typeof rec.turn_id === "string"
          && typeof rec.role === "string"
          && typeof rec.text === "string"
          && typeof rec.ts_ms === "number"
        );
      });
      this.chat.restoreHistory(turns);
    } catch (err) {
      logError("history", err);
    }
  }
}

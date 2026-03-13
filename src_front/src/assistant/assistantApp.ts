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
import {FrontendNatsClient, type NatsStatus} from "../net/natsClient";
import {CommandHandler} from "../core/commandHandler";
import {logError, logEvent, logReplayBundle} from "../core/logging";
import {DialogReplayCollector} from "../core/dialogReplayCollector";
import {AgentCommandHandler} from "../agentCommands/agentCommandHandler";
import {
  ClientHandlerCommand,
  CommandRequestTelemetryEvent,
  HistorySnapshotResponse,
  HistoryTurn,
  ServerEvent,
} from "../types";
import { MapController } from "../map/mapController";

/* ===========================
   AssistantApp
   =========================== */
export class AssistantApp {
  private static readonly SESSION_STORAGE_KEY = "assistant.session_id";
  private static readonly CHAT_ROUTE_PREFIX = "/chat";
  private static readonly UUID_RE =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  private el = getAssistantElements();

  private chat: ChatUI;
  private warning: WarningUI;
  private map = new MapController();

  private audio = createAudioState(this.el, this.config);
  private commands = new CommandHandler();

  private nats = new FrontendNatsClient();
  private natsReconnectTimer: number | null = null;
  private natsReconnectAttempt = 0;
  private natsStatusBound = false;

  private agentCommands: AgentCommandHandler;
  private modelStatuses = new Map<string, {status: string; percent?: number}>();
  private replayCollector: DialogReplayCollector;

  constructor(private config: AppConfig) {
    this.replayCollector = new DialogReplayCollector({
      maxItems: 10,
    });
    if (this.config.ui.debug) {
      this.commands.setTelemetryHook((event) => this.onCommandTelemetry(event));
    }

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
    this.initializeSessionId();
    window.addEventListener("popstate", () => this.handlePopState());
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
      const sessionId = await connectSession(
        this.config,
        this.el,
        this.audio,
        { sessionId: this.commands.getSessionId() },
      );
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
    if (!this.natsStatusBound) {
      this.nats.onStatus((s) => this.handleNatsStatus(s));
      this.natsStatusBound = true;
    }

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

  private handleNatsStatus(status: NatsStatus): void {
    if (status.type === "connected") {
      this.clearNatsReconnectTimer();
      this.natsReconnectAttempt = 0;
      setStatus(this.el, "События подключены");
      return;
    }

    if (status.type === "error") {
      logError("nats", status.error);
      setStatus(this.el, "NATS: ошибка, переподключение…");
      this.scheduleNatsReconnect();
      return;
    }

    setStatus(this.el, "NATS отключено, переподключение…");
    this.scheduleNatsReconnect();
  }

  private scheduleNatsReconnect(): void {
    if (this.natsReconnectTimer !== null) return;
    const delayMs = Math.min(15000, 1000 * 2 ** Math.min(this.natsReconnectAttempt, 4));
    this.natsReconnectAttempt += 1;

    this.natsReconnectTimer = window.setTimeout(() => {
      this.natsReconnectTimer = null;
      void this.reconnectNats();
    }, delayMs);
  }

  private clearNatsReconnectTimer(): void {
    if (this.natsReconnectTimer === null) return;
    window.clearTimeout(this.natsReconnectTimer);
    this.natsReconnectTimer = null;
  }

  private async reconnectNats(): Promise<void> {
    await this.nats.disconnect();
    await this.connectNats();
  }

  private handleNatsPayload(payload: string): void {
    try {
      const event = JSON.parse(payload) as ServerEvent;
      if (this.config.ui.debug) {
        this.emitReplayBundle(this.replayCollector.onNatsEvent(event));
      }
      void this.handleServerEvent(event);
    } catch (err) {
      if (this.config.ui.debug) {
        this.emitReplayBundle(
          this.replayCollector.onClientError("nats.parse", err),
        );
      }
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

  private initializeSessionId(): void {
    const fromRoute = this.readSessionIdFromRoute();
    if (fromRoute) {
      this.persistSessionId(fromRoute, { syncRoute: false });
      return;
    }

    const created = crypto.randomUUID();
    this.persistSessionId(created, { syncRoute: true, historyMode: "replace" });
  }

  private handlePopState(): void {
    const routeSessionId = this.readSessionIdFromRoute();
    if (!routeSessionId) {
      window.location.reload();
      return;
    }
    const currentSessionId = this.commands.getSessionId();
    if (!currentSessionId) return;
    if (routeSessionId === currentSessionId) return;
    window.location.reload();
  }

  private readSessionIdFromRoute(): string | null {
    const path = window.location.pathname || "";
    const routeRe = /^\/chat\/([^/]+)\/?$/;
    const match = path.match(routeRe);
    if (!match || !match[1]) return null;
    const decoded = decodeURIComponent(match[1]).trim();
    return this.isValidSessionId(decoded) ? decoded : null;
  }

  private setRouteSessionId(sessionId: string, historyMode: "replace" | "push"): void {
    const targetPath = `${AssistantApp.CHAT_ROUTE_PREFIX}/${encodeURIComponent(sessionId)}`;
    if (window.location.pathname === targetPath) return;
    const targetUrl = `${targetPath}${window.location.search}${window.location.hash}`;
    if (historyMode === "push") {
      window.history.pushState({}, "", targetUrl);
      return;
    }
    window.history.replaceState({}, "", targetUrl);
  }

  private isValidSessionId(value: string): boolean {
    return AssistantApp.UUID_RE.test(value.trim());
  }

  private persistSessionId(
    sessionId: string | null,
    options: { syncRoute?: boolean; historyMode?: "replace" | "push" } = {},
  ): void {
    if (!sessionId || !this.isValidSessionId(sessionId)) return;
    this.commands.setSessionId(sessionId);
    this.replayCollector.setSessionId(sessionId);
    sessionStorage.setItem(AssistantApp.SESSION_STORAGE_KEY, sessionId);
    if (options.syncRoute !== false) {
      this.setRouteSessionId(sessionId, options.historyMode ?? "replace");
    }
  }

  private onCommandTelemetry(event: CommandRequestTelemetryEvent): void {
    if (!this.config.ui.debug) return;
    this.emitReplayBundle(this.replayCollector.onHttpTelemetry(event));
  }

  private emitReplayBundle(bundle: unknown): void {
    if (!this.config.ui.debug) return;
    logReplayBundle(bundle);
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
      const data = (await resp.json()) as HistorySnapshotResponse;
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
      this.restoreArtifactsFromRuntimeContext(data.runtime_context);
    } catch (err) {
      logError("history", err);
    }
  }

  private restoreArtifactsFromRuntimeContext(runtimeContext: unknown): void {
    const context = this.toRecord(runtimeContext);
    if (!context) return;
    const artifact = this.toRecord(context["artifact_memory"]);
    if (!artifact) return;

    const airportsRaw = artifact["last_airports"];
    if (Array.isArray(airportsRaw)) {
      const airports: Array<{ lat: number; lon: number; id?: string; code?: string; name?: string; status?: string }> = [];
      for (const rowRaw of airportsRaw) {
        const row = this.toRecord(rowRaw);
        if (!row) continue;
        const lat = this.toNumber(row["lat"]);
        const lon = this.toNumber(row["lon"]);
        if (lat === null || lon === null) continue;
        airports.push({
          id: typeof row["id"] === "string" ? row["id"] : undefined,
          code: typeof row["code"] === "string" ? row["code"] : undefined,
          name: typeof row["name"] === "string" ? row["name"] : undefined,
          status: typeof row["status"] === "string" ? row["status"] : undefined,
          lat,
          lon,
        });
      }
      if (airports.length) this.map.setAirports(airports);
    }

    const positionRaw = this.toRecord(artifact["last_position"]);
    if (positionRaw) {
      const lat = this.toNumber(positionRaw["lat"]);
      const lon = this.toNumber(positionRaw["lon"]);
      if (lat !== null && lon !== null) {
        this.map.setCurrentPosition(lat, lon);
      }
    }

    const routeRaw = this.toRecord(artifact["last_route"]);
    if (routeRaw) {
      const geometryRaw = Array.isArray(routeRaw["geometry"]) ? routeRaw["geometry"] : [];
      const geometry = geometryRaw
        .map((point) => Array.isArray(point) ? point : null)
        .filter((point): point is unknown[] => Array.isArray(point) && point.length === 2)
        .map((point) => {
          const lon = this.toNumber(point[0]);
          const lat = this.toNumber(point[1]);
          if (lon === null || lat === null) return null;
          return [lon, lat] as [number, number];
        })
        .filter((point): point is [number, number] => Boolean(point));
      if (geometry.length) {
        const distanceKm = this.toNumber(routeRaw["distance_km"]);
        this.map.drawRoute({
          geometry,
          distance_km: distanceKm === null ? undefined : distanceKm,
        });
      }
    }
  }

  private toRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    return value as Record<string, unknown>;
  }

  private toNumber(value: unknown): number | null {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const parsed = Number(value.trim());
      if (Number.isFinite(parsed)) return parsed;
    }
    return null;
  }
}

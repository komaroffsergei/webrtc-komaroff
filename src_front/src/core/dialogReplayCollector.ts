import type {
  CommandRequestTelemetryEvent,
  ReplayBundle,
  ReplayFlowItem,
  ServerEvent,
} from "../types";

type ReplayCollectorOptions = {
  maxItems?: number;
};

const DEFAULT_MAX_ITEMS = 10;
const MAX_TEXT_LEN = 300;

export class DialogReplayCollector {
  private readonly maxItems: number;
  private sessionId: string | null = null;
  private flow: ReplayFlowItem[] = [];
  private dropped = 0;

  constructor(options: ReplayCollectorOptions = {}) {
    this.maxItems = Math.max(1, options.maxItems ?? DEFAULT_MAX_ITEMS);
  }

  setSessionId(sessionId: string | null): void {
    this.sessionId = cleanString(sessionId);
  }

  onHttpTelemetry(event: CommandRequestTelemetryEvent): ReplayBundle {
    this.sessionId = cleanString(event.session_id_after) ?? cleanString(event.request.session_id) ?? this.sessionId;
    const isEdit = Boolean(event.request.edit?.turn_id);

    const entry: ReplayFlowItem = {
      source: "http",
      action: isEdit ? "edit_message" : "send_message",
      phase: event.phase,
      turn_id: cleanString(event.request.turn_id),
      edit_turn_id: cleanString(event.request.edit?.turn_id),
      text: shortText(event.request.text),
      status_code: event.response_status,
      error: cleanString(event.error) ?? undefined,
    };
    this.push(entry);
    return this.buildBundle("http");
  }

  onNatsEvent(event: ServerEvent): ReplayBundle {
    const trace = extractTrace(event.data);
    this.sessionId = trace.session_id ?? this.sessionId;
    const entry = this.compactNatsEvent(event);
    this.push(entry);
    return this.buildBundle("nats");
  }

  onClientError(source: string, error: unknown): ReplayBundle {
    this.push({
      source: "client",
      action: "client_error",
      details: { source },
      error: stringifyError(error),
    });
    return this.buildBundle("client_error");
  }

  private compactNatsEvent(event: ServerEvent): ReplayFlowItem {
    const base: ReplayFlowItem = {
      source: "nats",
      action: `${event.type}/${event.kind}${event.name ? `:${event.name}` : ""}`,
      service: cleanString(event.service) ?? undefined,
    };

    if (event.service === "src_llm" && event.name === "llm_request_debug") {
      return this.compactLlmRequest(event, base);
    }

    if (event.service === "src_llm" && event.name === "llm_result") {
      return this.compactLlmResult(event, base);
    }

    if (event.kind === "thought") {
      return this.compactThought(event, base);
    }

    if (event.kind === "client") {
      return this.compactClientCommand(event, base);
    }

    if (event.kind === "voice") {
      const blocked = typeof event.data.blocked === "boolean" ? event.data.blocked : undefined;
      return { ...base, blocked };
    }

    if (event.kind === "message" || event.kind === "transcription") {
      const text = typeof event.data.text === "string" ? shortText(event.data.text) : undefined;
      const turnId = cleanString((event.data as Record<string, unknown>).turn_id);
      return {
        ...base,
        text,
        turn_id: turnId ?? undefined,
      };
    }

    if (event.type === "log") {
      const text = typeof event.data.text === "string" ? shortText(event.data.text) : undefined;
      return text ? { ...base, text } : base;
    }

    return base;
  }

  private compactLlmRequest(event: ServerEvent, base: ReplayFlowItem): ReplayFlowItem {
    const payload = toRecord(event.data.payload);
    const mode = cleanString(payload?.mode);
    const input = toRecord(payload?.input);
    const details: Record<string, unknown> = {};

    const userText = cleanString(input?.user_message) ?? cleanString(input?.text);
    if (userText) details.user_text = shortText(userText);

    const toolName = cleanString(input?.tool_name);
    if (toolName) details.tool_name = toolName;

    const scenarioContext = cleanString(input?.scenario_context);
    if (scenarioContext) details.scenario_context = shortText(scenarioContext);

    const resolvedMode = cleanString(input?.resolved_reference_mode);
    if (resolvedMode) details.resolved_reference_mode = resolvedMode;

    const freeSpeechPass = cleanString(input?.free_speech_pass);
    if (freeSpeechPass) details.free_speech_pass = freeSpeechPass;

    const retryReason = cleanString(input?.retry_reason);
    if (retryReason) details.retry_reason = retryReason;

    return {
      ...base,
      mode: mode ?? undefined,
      details: Object.keys(details).length ? details : undefined,
    };
  }

  private compactLlmResult(event: ServerEvent, base: ReplayFlowItem): ReplayFlowItem {
    const payload = toRecord(event.data.payload);
    const data = toRecord(payload?.data);
    const workflow = cleanString(data?.workflow_id);
    const responseText = cleanString(data?.response_text);
    const prompt = cleanString(data?.prompt);
    const missingRaw = data?.missing;
    const missing = Array.isArray(missingRaw)
      ? missingRaw
          .filter((x) => typeof x === "string")
          .map((x) => x.trim())
          .filter(Boolean)
      : undefined;
    const extracted = toRecord(data?.extracted) ?? undefined;

    const details: Record<string, unknown> = {};
    const reason = cleanString(data?.reason);
    const confidence = numeric(data?.confidence);
    if (reason) details.reason = shortText(reason);
    if (confidence !== null) details.confidence = confidence;

    return {
      ...base,
      workflow: workflow ?? undefined,
      text: responseText ? shortText(responseText) : undefined,
      prompt: prompt ? shortText(prompt) : undefined,
      missing: missing && missing.length ? missing : undefined,
      extracted,
      details: Object.keys(details).length ? details : undefined,
    };
  }

  private compactThought(event: ServerEvent, base: ReplayFlowItem): ReplayFlowItem {
    const scenario = toRecord((event.data as Record<string, unknown>).scenario);
    const details: Record<string, unknown> = {};
    const summary = cleanString((event.data as Record<string, unknown>).summary);
    const content = cleanString((event.data as Record<string, unknown>).content);
    if (summary) details.summary = shortText(summary);
    if (content) details.content = shortText(content);

    return {
      ...base,
      scenario: cleanString(scenario?.id) ?? undefined,
      details: Object.keys(details).length ? details : undefined,
    };
  }

  private compactClientCommand(event: ServerEvent, base: ReplayFlowItem): ReplayFlowItem {
    const command = cleanString((event.data as Record<string, unknown>).command);
    const artifacts = toRecord((event.data as Record<string, unknown>).artifacts);
    const uiPayload = toRecord(toRecord(artifacts?.payload)?.ui);

    const turnId = cleanString(uiPayload?.user_turn_id) ?? cleanString(uiPayload?.assistant_turn_id);
    const message = cleanString(uiPayload?.message) ?? cleanString(uiPayload?.summary) ?? cleanString(uiPayload?.prompt);

    return {
      ...base,
      command: command ?? undefined,
      turn_id: turnId ?? undefined,
      text: message ? shortText(message) : undefined,
    };
  }

  private buildBundle(trigger: string): ReplayBundle {
    return {
      schema: "dialog_replay@2",
      session_id: this.sessionId,
      trigger,
      flow: copy(this.flow),
      dropped: this.dropped,
    };
  }

  private push(item: ReplayFlowItem): void {
    this.flow.push(copy(item));
    while (this.flow.length > this.maxItems) {
      this.flow.shift();
      this.dropped += 1;
    }
  }
}

function extractTrace(data: Record<string, unknown>): { session_id: string | null } {
  const direct = toRecord(data.trace);
  if (direct) {
    return {
      session_id: cleanString(direct.session_id),
    };
  }
  const payload = toRecord(data.payload);
  return {
    session_id: cleanString(payload?.session_id),
  };
}

function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function shortText(value: string): string {
  const clean = value.replace(/\s+/g, " ").trim();
  if (clean.length <= MAX_TEXT_LEN) return clean;
  return `${clean.slice(0, MAX_TEXT_LEN - 12)}...<truncated>`;
}

function cleanString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const out = value.trim();
  return out || null;
}

function stringifyError(error: unknown): string {
  if (error instanceof Error) return error.message || error.name || "Error";
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function numeric(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function copy<T>(value: T): T {
  try {
    return JSON.parse(JSON.stringify(value)) as T;
  } catch {
    return value;
  }
}

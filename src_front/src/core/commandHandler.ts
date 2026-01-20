type CommandHandlerFn = (params: unknown, uid?: string) => void | Promise<void>;

export class CommandHandler {
  private handlers = new Map<string, CommandHandlerFn>();
  private sessionId: string | null = null;

  register(method: string, handler: CommandHandlerFn): void {
    this.handlers.set(method, handler);
  }

  setSessionId(sessionId: string | null): void {
    this.sessionId = sessionId;
  }

  // async handleServerEvent(event: ServerEvent): Promise<boolean> {
  //   if (event && "type" in event && event.type === "command" && event.method) {
  //     const h = this.handlers.get(event.method);
  //     if (!h) {
  //       logEvent({ service: "command", type: "warn", message: `No handler for ${event.method}` });
  //       return true;
  //     }
  //     try {
  //       await h(event.params, event.uid);
  //     } catch (err) {
  //       logEvent({
  //         service: "command",
  //         type: "error",
  //         message: `Handler ${event.method} failed: ${err instanceof Error ? err.message : String(err)}`,
  //       });
  //     }
  //     return true;
  //   }
  //
  //   return false;
  // }

  async sendMessage(text: string): Promise<void> {
    const resp = await fetch("/core/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: this.sessionId }),
    });
    if (!resp.ok) throw new Error(`Server responded with ${resp.status}`);
    try {
      const data = (await resp.json()) as { session_id?: unknown };
      this.sessionId = typeof data.session_id === "string" ? data.session_id : this.sessionId;
    } catch {
      // Ignore invalid/non-JSON responses.
    }
  }

  async sendEditedMessage(text: string, turnId: string): Promise<void> {
    const resp = await fetch("/core/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        session_id: this.sessionId,
        edit: { turn_id: turnId },
      }),
    });
    if (!resp.ok) throw new Error(`Server responded with ${resp.status}`);
    try {
      const data = (await resp.json()) as { session_id?: unknown };
      this.sessionId = typeof data.session_id === "string" ? data.session_id : this.sessionId;
    } catch {
      // Ignore invalid/non-JSON responses.
    }
  }
}

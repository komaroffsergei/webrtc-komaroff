import { connect, type Connection } from "@provide/nats.ws";

export type NatsClientOptions = {
  url: string;
  name?: string;
  user?: string;
  pass?: string;
  token?: string;
};

export type NatsStatus =
  | { type: "connected" }
  | { type: "error"; error: Error }
  | { type: "closed" };

type StatusHandler = (status: NatsStatus) => void;

export class FrontendNatsClient {
  private connection: Connection | null = null;
  private connectPromise: Promise<boolean> | null = null;
  private statusHandlers = new Set<StatusHandler>();
  private subscribedSubjects = new Set<string>();

  async connect(options: NatsClientOptions): Promise<boolean> {
    if (this.connection) return false;
    if (this.connectPromise) return this.connectPromise;

    this.connectPromise = this.openConnection(options);
    try {
      return await this.connectPromise;
    } finally {
      this.connectPromise = null;
    }
  }

  async disconnect(): Promise<void> {
    this.connectPromise = null;
    const conn = this.connection;
    this.resetConnectionState();
    if (!conn) return;
    try {
      await Promise.resolve((conn as any).close?.());
    } catch {
      // Ignore close errors during reconnect attempts.
    }
  }

  onStatus(handler: StatusHandler): void {
    this.statusHandlers.add(handler);
  }

  async subscribe(
    subject: string,
    handler: (payload: string) => void,
  ): Promise<void> {
    if (!this.connection) {
      throw new Error("NATS connection is not ready");
    }
    if (this.subscribedSubjects.has(subject)) {
      return;
    }
    await this.connection.subscribe(subject, (msg: any) => {
      const payload = this.decodePayload(msg);
      handler(payload);
    });
    this.subscribedSubjects.add(subject);
  }

  private async openConnection(options: NatsClientOptions): Promise<boolean> {
    const conn = await connect({
      url: options.url,
      name: options.name,
      user: options.user,
      pass: options.pass,
      token: options.token,
      payload: "string" as any,
    });
    this.connection = conn;
    this.subscribedSubjects.clear();
    this.bindConnectionListeners(conn);
    this.emitStatus({ type: "connected" });
    return true;
  }

  private bindConnectionListeners(conn: Connection): void {
    conn.addEventListener(
      "error",
      ((err: Error) => {
        if (this.connection !== conn) return;
        this.emitStatus({ type: "error", error: err });
        if (!isStaleConnectionError(err)) return;
        this.resetConnectionState();
        this.emitStatus({ type: "closed" });
        void Promise.resolve((conn as any).close?.()).catch(() => undefined);
      }) as any,
    );

    conn.addEventListener(
      "close",
      (() => {
        if (this.connection !== conn) return;
        this.resetConnectionState();
        this.emitStatus({ type: "closed" });
      }) as any,
    );
  }

  private decodePayload(msg: any): string {
    if (typeof msg.data === "string") {
      return msg.data;
    }
    if (msg.data instanceof Uint8Array) {
      return new TextDecoder("utf-8").decode(msg.data);
    }
    if (msg.data === undefined || msg.data === null) {
      return "";
    }
    try {
      return JSON.stringify(msg.data);
    } catch {
      return String(msg.data);
    }
  }

  private emitStatus(status: NatsStatus): void {
    this.statusHandlers.forEach((handler) => {
      try {
        handler(status);
      } catch (err) {
        console.warn("[nats] status handler failed", err);
      }
    });
  }

  private resetConnectionState(): void {
    this.connection = null;
    this.subscribedSubjects.clear();
  }
}

function isStaleConnectionError(error: Error): boolean {
  const message = `${error?.name ?? ""} ${error?.message ?? ""}`.toLowerCase();
  return message.includes("stale connection");
}

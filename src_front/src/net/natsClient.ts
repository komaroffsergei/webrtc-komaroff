import { connect, type Connection } from "@provide/nats.ws";

export type NatsClientOptions = {
  url: string;
  name?: string;
};

export type NatsStatus =
  | { type: "connected" }
  | { type: "error"; error: Error }
  | { type: "closed" };

type StatusHandler = (status: NatsStatus) => void;

export class FrontendNatsClient {
  private connection: Connection | null = null;
  private statusHandlers = new Set<StatusHandler>();

  async connect(options: NatsClientOptions): Promise<boolean> {
    if (this.connection) {
      return false;
    }
    this.connection = await connect({
      url: options.url,
      name: options.name,
      payload: "string" as any,
    });
    this.emitStatus({ type: "connected" });

    this.connection.addEventListener(
      "error",
      ((err: Error) => {
        this.emitStatus({ type: "error", error: err });
      }) as any,
    );

    this.connection.addEventListener(
      "close",
      (() => {
        this.emitStatus({ type: "closed" });
        this.connection = null;
      }) as any,
    );
    return true;
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
    await this.connection.subscribe(subject, (msg: any) => {
      const payload = this.decodePayload(msg);
      handler(payload);
    });
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
}

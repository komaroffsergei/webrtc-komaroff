import { connect } from '@provide/nats.ws';

// простой JSON-кодек, потому что в библиотеке его нет
const jc = {
  encode(obj: any): Uint8Array {
    return new TextEncoder().encode(JSON.stringify(obj));
  },

  decode(buf: Uint8Array): any {
    return JSON.parse(new TextDecoder().decode(buf));
  },
};

export type NatsLogEntry = {
  time: string;
  service: string;
  type: string;
  message: string;
  name?: string;
};

export type NatsMessage = {
  type: string;
  name?: string;
  message: string;
  [key: string]: any;
};

export class NatsClient {
  private nc: any;
  private readonly eventsSubject: string;
  private readonly agentSubject: string;
  private messageCallback: ((msg: NatsMessage) => void) | null = null;
  private logCallback: ((entry: NatsLogEntry) => void) | null = null;

  constructor(eventsSubject: string, agentSubject: string) {
    this.eventsSubject = eventsSubject;
    this.agentSubject = agentSubject;
  }

  async connect(url: string): Promise<void> {
    this.nc = await connect({ servers: [url] });
    console.log('NATS connected');

    // подписка на события
    await this.nc.subscribe(this.eventsSubject, {
      callback: (err: any, msg: any) => {
        if (err) return;

        try {
          const data = jc.decode(msg.data);

          if (this.logCallback) this.logCallback(data);
          if (this.messageCallback && data.type === 'message') {
            this.messageCallback(data);
          }
        } catch (e) {
          console.warn('NATS message parse error', e);
        }
      },
    });
  }

  onMessage(cb: (msg: NatsMessage) => void): void {
    this.messageCallback = cb;
  }

  onLog(cb: (entry: NatsLogEntry) => void): void {
    this.logCallback = cb;
  }

  send(payload: { text: string }): void {
    const data = jc.encode(payload);
    this.nc.publish(this.agentSubject, data);
  }
}

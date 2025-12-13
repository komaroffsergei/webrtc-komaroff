import type { AppConfig } from "../config/appConfig";
import { createEnergyVAD, type VADInstance } from "./vad";

export class VADController {
  private vad: VADInstance | null = null;

  constructor(private config: AppConfig) {}

  stop(): void {
    this.vad?.cleanup();
    this.vad = null;
  }

  apply(
    track: MediaStreamTrack,
    sender: RTCRtpSender,
    getThreshold: () => number,
    onThresholdText?: (value: number) => void,
  ): void {
    this.stop();

    this.vad = createEnergyVAD(track, this.config, getThreshold, onThresholdText);

    sender.replaceTrack(this.vad.track).catch((err) => {
      console.warn("replaceTrack failed", err);
    });
  }
}

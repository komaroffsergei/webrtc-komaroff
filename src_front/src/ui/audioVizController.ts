import {
  attachAnalyserDraw,
  createWaveDrawer,
  type AnalyserConfig,
  type CanvasConfig,
} from "../core/audioViz";
import type { AssistantElements } from "./elements";

type CanvasViz = { stop: () => void } | null;

export class AudioVizController {
  private backgroundViz: CanvasViz = null;
  private micViz: CanvasViz = null;

  constructor(private elements: AssistantElements) {}

  setupCanvasSizes(): void {
    const canvas = this.elements.waveBackground;
    const container = this.elements.chatWindow;

    if (canvas && container) {
      const rect = container.getBoundingClientRect();
      canvas.width = rect.width + 20;
      canvas.height = rect.height + 20;
    }

    if (this.elements.micWaveform) {
      this.elements.micWaveform.width = 140;
      this.elements.micWaveform.height = 40;
    }
  }

  attach(stream: MediaStream): void {
    this.setupBackgroundWaveform(stream);
    this.setupMicWaveform(stream);
  }

  stop(): void {
    this.backgroundViz?.stop();
    this.backgroundViz = null;

    this.micViz?.stop();
    this.micViz = null;
  }

  private setupBackgroundWaveform(stream: MediaStream): void {
    if (!this.elements.waveBackground) return;

    const ctx = this.elements.waveBackground.getContext("2d");
    if (!ctx) return;

    this.backgroundViz?.stop();

    const canvasConfig: CanvasConfig = {
      width: this.elements.waveBackground.width,
      height: this.elements.waveBackground.height,
      gridColor: "transparent",
    };

    const analyserConfig: AnalyserConfig = {
      fftSize: 512,
      historySeconds: 3,
    };

    const drawer = createWaveDrawer(ctx, canvasConfig);
    const audioContext = new (window.AudioContext ||
      (window as any).webkitAudioContext)();

    this.backgroundViz = attachAnalyserDraw(
      audioContext,
      stream,
      analyserConfig,
      (history) => drawer(history, "#007aff"),
    );
  }

  private setupMicWaveform(stream: MediaStream): void {
    if (!this.elements.micWaveform) return;

    const ctx = this.elements.micWaveform.getContext("2d");
    if (!ctx) return;

    this.micViz?.stop();

    const canvasConfig: CanvasConfig = {
      width: this.elements.micWaveform.width,
      height: this.elements.micWaveform.height,
      gridColor: "transparent",
    };

    const analyserConfig: AnalyserConfig = {
      fftSize: 256,
      historySeconds: 0.5,
    };

    const drawer = createWaveDrawer(ctx, canvasConfig);
    const audioContext = new (window.AudioContext ||
      (window as any).webkitAudioContext)();

    this.micViz = attachAnalyserDraw(audioContext, stream, analyserConfig, (history) =>
      drawer(history, "#fff"),
    );
  }
}

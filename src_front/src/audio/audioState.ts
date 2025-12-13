import type { AppConfig } from "../config/appConfig";
import type { AssistantElements } from "../ui/elements";

export type AudioState = {
  vadEnabled: boolean;
  vadThreshold: number;
  echoCancellation: boolean;
  noiseSuppression: boolean;
};

export function createAudioState(
  el: AssistantElements,
  config: AppConfig,
): AudioState {
  const s: AudioState = {
    vadEnabled: el.vadEnable?.checked ?? true,
    vadThreshold: el.vadThresh?.valueAsNumber ?? -55,
    echoCancellation: el.ecEnable?.checked ?? config.audio.input.echoCancellationDefault,
    noiseSuppression: el.nsEnable?.checked ?? config.audio.input.noiseSuppressionDefault,
  };

  el.vadEnable?.addEventListener("change", () => (s.vadEnabled = el.vadEnable!.checked));
  el.vadThresh?.addEventListener("input", () => (s.vadThreshold = el.vadThresh!.valueAsNumber));
  el.ecEnable?.addEventListener("change", () => (s.echoCancellation = el.ecEnable!.checked));
  el.nsEnable?.addEventListener("change", () => (s.noiseSuppression = el.nsEnable!.checked));

  return s;
}

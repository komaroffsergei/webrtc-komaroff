import type { AppConfig } from "../config/appConfig";
import type { AssistantElements } from "../ui/elements";

export type AudioState = {
  echoCancellation: boolean;
  noiseSuppression: boolean;
};

export function createAudioState(
  el: AssistantElements,
  config: AppConfig,
): AudioState {
  const s: AudioState = {
    echoCancellation: el.ecEnable?.checked ?? config.audio.input.echoCancellationDefault,
    noiseSuppression: el.nsEnable?.checked ?? config.audio.input.noiseSuppressionDefault,
  };

  el.ecEnable?.addEventListener("change", () => (s.echoCancellation = el.ecEnable!.checked));
  el.nsEnable?.addEventListener("change", () => (s.noiseSuppression = el.nsEnable!.checked));

  return s;
}

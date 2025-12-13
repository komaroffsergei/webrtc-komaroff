export type AssistantElements = {
  container: HTMLElement | null;
  chatWindow: HTMLElement | null;
  messageLog: HTMLElement | null;
  textInput: HTMLInputElement | null;
  micButton: HTMLButtonElement | null;
  micWaveform: HTMLCanvasElement | null;
  waveBackground: HTMLCanvasElement | null;
  connectionStatus: HTMLElement | null;
  remoteAudio: HTMLAudioElement | null;

  vadEnable: HTMLInputElement | null;
  vadThresh: HTMLInputElement | null;
  vadLevel: HTMLElement | null;
  ecEnable: HTMLInputElement | null;
  nsEnable: HTMLInputElement | null;
};

export function getAssistantElements(): AssistantElements {
  return {
    container: document.getElementById("assistantContainer") as HTMLElement | null,
    chatWindow: document.querySelector(".chat-window") as HTMLElement | null,
    messageLog: document.getElementById("messageLog") as HTMLElement | null,
    textInput: document.getElementById("textInput") as HTMLInputElement | null,
    micButton: document.getElementById("micButton") as HTMLButtonElement | null,
    micWaveform: document.getElementById("micWaveform") as HTMLCanvasElement | null,
    waveBackground: document.getElementById("waveBackground") as HTMLCanvasElement | null,
    connectionStatus: document.getElementById("connectionStatus") as HTMLElement | null,
    remoteAudio: document.getElementById("remoteAudio") as HTMLAudioElement | null,

    vadEnable: document.getElementById("vadEnable") as HTMLInputElement | null,
    vadThresh: document.getElementById("vadThresh") as HTMLInputElement | null,
    vadLevel: document.getElementById("vadLevel") as HTMLElement | null,
    ecEnable: document.getElementById("ecEnable") as HTMLInputElement | null,
    nsEnable: document.getElementById("nsEnable") as HTMLInputElement | null,
  };
}

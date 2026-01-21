import { appConfig } from "./config/appConfig";
import { AssistantApp } from "./assistant/assistantApp";
import "./styles/assistant.css";
import "maplibre-gl/dist/maplibre-gl.css";
import { Buffer } from "buffer";
(globalThis as any).Buffer = Buffer;
function boot() {
  new AssistantApp(appConfig).start();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}

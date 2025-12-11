import { Buffer } from "buffer";
import { appConfig } from "./config/appConfig";
import "./styles/assistant.css";
import { AssistantApp } from "./assistant/assistantApp";

if (typeof (globalThis as any).Buffer === "undefined") {
  (globalThis as any).Buffer = Buffer;
}

const bootstrap = () => {
  const app = new AssistantApp(appConfig);
  app.start();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}

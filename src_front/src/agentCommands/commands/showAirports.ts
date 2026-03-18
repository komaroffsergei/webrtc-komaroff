import {AgentCommandContext, ClientHandlerCommand} from "../../types";
import { readLastArtifactData } from "./payload";

type Runway = {
  id?: string;
  length_m?: number;
  surface?: string;
  status?: string;
};

type Airport = {
  id?: string;
  code?: string;
  name?: string;
  lat?: number;
  lon?: number;
  status?: string;
  distance_km?: number;
  runways?: Runway[];
};

function isAirport(x: unknown): x is Airport {
  return typeof x === "object" && x !== null;
}

export function handleShowAirports(
  message: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const data = readLastArtifactData(message);
  const airportsValue = data.airports;
  if (airportsValue && !Array.isArray(airportsValue)) {
    ctx.chat.addMessage("Аэропорты не найдены.", "server");
    return;
  }

  const airports = Array.isArray(airportsValue)
    ? (airportsValue.filter(isAirport) as Airport[])
    : undefined;
  if (!airports || airports.length === 0) {
    ctx.chat.addMessage("Аэропорты не найдены.", "server");
    return;
  }

  const lines = airports.map((a) => {
    const code = a.code ?? a.id ?? "???";
    const name = a.name ?? "";
    const status = a.status ? `(${a.status})` : "";
    const dist =
      typeof a.distance_km === "number" ? `${a.distance_km.toFixed(1)} км` : "";

    const runways = Array.isArray(a.runways)
      ? a.runways
          .map((r) => {
            const rid = r.id ?? "RWY";
            const len = typeof r.length_m === "number" ? `${r.length_m}м` : "";
            const st = r.status ? `/${r.status}` : "";
            return `${rid} ${len}${st}`.trim();
          })
          .join(", ")
      : "";

    return `• ${code} ${name} ${status} ${dist}\n  ВПП: ${runways || "—"}`;
  });

  ctx.chat.addMessage(lines.join("\n"), "server");
}

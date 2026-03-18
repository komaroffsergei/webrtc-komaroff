import {AgentCommandContext, ClientHandlerCommand} from "../../types";
import { readLastArtifactData } from "./payload";

type Airport = {
  id?: string;
  code?: string;
  name?: string;
  lat?: number;
  lon?: number;
  status?: string;
};

function isAirport(x: unknown): x is Airport {
  if (!x || typeof x !== "object") return false;
  const rec = x as Record<string, unknown>;
  return typeof rec.lat === "number" && typeof rec.lon === "number";
}

export function handleSetAirports(resp: ClientHandlerCommand, ctx: AgentCommandContext): void {
  const airportsRaw = readLastArtifactData(resp).airports;
  if (!Array.isArray(airportsRaw)) return;

  const airports = airportsRaw.filter(isAirport) as Airport[];
  if (!airports.length) return;

  ctx.map?.setAirports(
    airports.map((a) => ({
      id: a.id,
      code: a.code,
      name: a.name,
      lat: a.lat!,
      lon: a.lon!,
      status: a.status,
    })),
  );
}

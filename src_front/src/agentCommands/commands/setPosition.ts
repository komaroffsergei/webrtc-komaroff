import {AgentCommandContext, ClientHandlerCommand} from "../../types";
import { readLastArtifactData } from "./payload";

export function handleSetPosition(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const posValue = readLastArtifactData(resp).current_position;
  const pos =
    posValue && typeof posValue === "object"
      ? (posValue as Record<string, unknown>)
      : null;
  const lat = pos && typeof pos.lat === "number" ? pos.lat : null;
  const lon = pos && typeof pos.lon === "number" ? pos.lon : null;
  if (lat === null || lon === null) return;
  ctx.map?.setCurrentPosition(lat, lon);
}

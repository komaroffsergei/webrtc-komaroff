import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export function handleSetPosition(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const artifacts = resp.artifacts;
  const key = artifacts?.last ?? null;
  const raw = key ? (artifacts?.payload as any)?.[key] : null;
  const pos = raw?.data?.current_position;
  const lat = typeof pos?.lat === "number" ? pos.lat : null;
  const lon = typeof pos?.lon === "number" ? pos.lon : null;
  if (lat === null || lon === null) return;
  ctx.map?.setCurrentPosition(lat, lon);
}

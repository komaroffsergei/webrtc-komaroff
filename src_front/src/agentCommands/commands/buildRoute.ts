import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export function handleBuildRoute(
  resp: ClientHandlerCommand,
  ctx: AgentCommandContext,
): void {
  const artifacts = resp.artifacts;
  const key = artifacts?.last ?? null;
  const raw = key ? (artifacts?.payload as any)?.[key] : null;
  const route = raw?.data?.route;
  const geometry = Array.isArray(route?.geometry) ? route.geometry : null;
  if (!geometry || !geometry.length) return;

  const coords = geometry.filter(
    (p: unknown): p is [number, number] =>
      Array.isArray(p) && p.length === 2 && typeof p[0] === "number" && typeof p[1] === "number",
  );
  if (!coords.length) return;

  const distance = typeof route?.distance_km === "number" ? route.distance_km : undefined;
  ctx.map?.drawRoute({ geometry: coords, distance_km: distance });
}

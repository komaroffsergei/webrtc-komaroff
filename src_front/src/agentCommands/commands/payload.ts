import type { ClientHandlerCommand } from "../../types";

export function readLastArtifactPayload(resp: ClientHandlerCommand): Record<string, unknown> {
  const artifacts = resp.artifacts?.payload ?? {};
  const last = resp.artifacts?.last;
  return last && artifacts[last] ? (artifacts[last] as Record<string, unknown>) : {};
}

export function readLastArtifactData(resp: ClientHandlerCommand): Record<string, unknown> {
  const payload = readLastArtifactPayload(resp);
  const data = payload.data;
  return data && typeof data === "object" ? (data as Record<string, unknown>) : {};
}

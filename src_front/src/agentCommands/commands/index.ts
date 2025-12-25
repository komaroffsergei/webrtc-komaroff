import type { AgentCommandContext, AgentResponse } from "../types";
import { handleShowAirports } from "./showAirports";
import { handleSetPosition } from "./setPosition";
import { handleBuildRoute } from "./buildRoute";
import { handleShowErrorMessage } from "./showErrorMessage";

export type CommandHandlerFn = (resp: AgentResponse, ctx: AgentCommandContext) => void;

export const commandHandlers: Record<string, CommandHandlerFn> = {
  SHOW_AIRPORTS: handleShowAirports,
  SET_POSITION: handleSetPosition,
  BUILD_ROUTE: handleBuildRoute,
  SHOW_ERROR_MESSAGE: handleShowErrorMessage,
};

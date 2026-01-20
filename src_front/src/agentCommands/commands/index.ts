import { handleShowAirports } from "./showAirports";
import { handleSetPosition } from "./setPosition";
import { handleBuildRoute } from "./buildRoute";
import { handleShowErrorMessage } from "./showErrorMessage";
import { handleShowMessage } from "./showMessage";
import {AgentCommandContext, ClientHandlerCommand} from "../../types";

export type CommandHandlerFn = (resp: ClientHandlerCommand, ctx: AgentCommandContext) => void;

export const commandHandlers: Record<string, CommandHandlerFn> = {
  SHOW_AIRPORTS: handleShowAirports,
  SET_POSITION: handleSetPosition,
  BUILD_ROUTE: handleBuildRoute,
  SHOW_ERROR_MESSAGE: handleShowErrorMessage,
  ASK_USER_INPUT: handleShowMessage,
  SHOW_MESSAGE: handleShowMessage,
};

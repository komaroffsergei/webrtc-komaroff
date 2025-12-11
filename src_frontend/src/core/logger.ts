export const logger = {
  debugMode: false,

  enableDebug(): void {
    this.debugMode = true;
  },

  info(message: string): void {
    console.info(message);
  },

  debug(message: string): void {
    if (this.debugMode) {
      console.debug(message);
    }
  },
};

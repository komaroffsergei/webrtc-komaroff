import { logger } from '../core/logger';

export class VoiceAssistant {
  start() {
    logger.info('Voice assistant started');
  }

  stop() {
    logger.info('Voice assistant stopped');
  }
}

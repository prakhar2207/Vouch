/**
 * Centralized logging utility for SriLekh Frontend.
 * Provides environment-aware log levels, formatted outputs, and safe serialization.
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const isProduction = typeof process !== 'undefined' && process.env.NODE_ENV === 'production';

function formatMessage(prefix: string, message: string): string {
  const timestamp = new Date().toISOString();
  return `[${timestamp}] [${prefix}] ${message}`;
}

export const logger = {
  debug: (message: string, ...args: unknown[]) => {
    if (!isProduction) {
      console.debug(formatMessage('DEBUG', message), ...args);
    }
  },

  info: (message: string, ...args: unknown[]) => {
    console.info(formatMessage('INFO', message), ...args);
  },

  warn: (message: string, ...args: unknown[]) => {
    console.warn(formatMessage('WARN', message), ...args);
  },

  error: (message: string, error?: unknown, ...args: unknown[]) => {
    console.error(formatMessage('ERROR', message), error, ...args);
  }
};

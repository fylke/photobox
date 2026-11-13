type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

interface LogEntry {
  level: LogLevel;
  timestamp: string;
  message: string;
  data?: unknown;
}

class Logger {
  private logs: LogEntry[] = [];
  private maxLogs = 5000;
  private listeners: ((log: LogEntry) => void)[] = [];
  private debugMode = this.isDebugMode();

  constructor() {
    this.syncDebugMode();
  }

  private isDebugMode(): boolean {
    const params = new URLSearchParams(window.location.search);
    return params.get('debug') === 'true' || localStorage.getItem('debug-mode') === 'true';
  }

  private syncDebugMode(): void {
    const params = new URLSearchParams(window.location.search);
    if (params.get('debug') === 'true') {
      localStorage.setItem('debug-mode', 'true');
      this.debugMode = true;
    }
  }

  setDebugMode(enabled: boolean): void {
    this.debugMode = enabled;
    if (enabled) {
      localStorage.setItem('debug-mode', 'true');
    } else {
      localStorage.removeItem('debug-mode');
    }
  }

  isDebugEnabled(): boolean {
    return this.debugMode;
  }

  subscribe(listener: (log: LogEntry) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private log(level: LogLevel, message: string, data?: unknown): void {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const ms = String(now.getMilliseconds()).padStart(3, '0');
    const timestamp = `${hours}:${minutes}:${seconds}.${ms}`;

    const entry: LogEntry = { level, timestamp, message, data };

    if (this.logs.length >= this.maxLogs) {
      this.logs.shift();
    }
    this.logs.push(entry);

    const consoleLevel = level === 'ERROR' ? 'error' : level === 'WARN' ? 'warn' : 'log';
    console[consoleLevel](
      `[${timestamp}] ${level} - ${message}`,
      data ? data : ''
    );

    this.listeners.forEach((listener) => listener(entry));
  }

  debug(message: string, data?: unknown): void {
    if (this.debugMode) {
      this.log('DEBUG', message, data);
    }
  }

  info(message: string, data?: unknown): void {
    this.log('INFO', message, data);
  }

  warn(message: string, data?: unknown): void {
    this.log('WARN', message, data);
  }

  error(message: string, data?: unknown): void {
    this.log('ERROR', message, data);
  }

  getLogs(): LogEntry[] {
    return [...this.logs];
  }

  clearLogs(): void {
    this.logs = [];
  }

  exportLogs(): string {
    return this.logs
      .map(
        (log) =>
          `[${log.timestamp}] ${log.level} - ${log.message}${
            log.data ? ' ' + JSON.stringify(log.data) : ''
          }`
      )
      .join('\n');
  }
}

export const logger = new Logger();

import React, { useEffect, useState } from 'react';
import { logger } from '../utils/logger';

interface LogEntry {
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
  timestamp: string;
  message: string;
}

const DebugPanel: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const logsRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsubscribe = logger.subscribe((entry) => {
      setLogs((prev) => [...prev, entry]);
    });

    setLogs(logger.getLogs());
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  const getLogColor = (level: string) => {
    switch (level) {
      case 'ERROR':
        return '#ef4444';
      case 'WARN':
        return '#f59e0b';
      case 'INFO':
        return '#ffffff';
      case 'DEBUG':
        return '#9ca3af';
      default:
        return '#ffffff';
    }
  };

  const handleExport = () => {
    const exported = logger.exportLogs();
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(exported));
    element.setAttribute('download', 'photobox-imager-debug.txt');
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#1a1a1a',
        borderRadius: '0.5rem',
        overflow: 'hidden',
        minWidth: '300px',
      }}
    >
      <div
        style={{
          padding: '0.75rem',
          borderBottom: '1px solid #333',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ color: '#9ca3af', fontSize: '0.85rem', fontWeight: '600' }}>
          Debug Log ({logs.length})
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handleExport}
            style={{
              padding: '0.25rem 0.5rem',
              fontSize: '0.75rem',
              backgroundColor: '#333',
              color: '#9ca3af',
              border: '1px solid #444',
              borderRadius: '0.25rem',
            }}
          >
            Export
          </button>
          <button
            onClick={() => logger.clearLogs()}
            style={{
              padding: '0.25rem 0.5rem',
              fontSize: '0.75rem',
              backgroundColor: '#333',
              color: '#9ca3af',
              border: '1px solid #444',
              borderRadius: '0.25rem',
            }}
          >
            Clear
          </button>
        </div>
      </div>

      <div
        ref={logsRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          fontFamily: 'Courier New, monospace',
          fontSize: '0.75rem',
          padding: '0.5rem',
          lineHeight: '1.3',
        }}
      >
        {logs.map((log, i) => (
          <div key={i} style={{ color: getLogColor(log.level), marginBottom: '0.25rem' }}>
            <span style={{ color: '#6b7280' }}>[{log.timestamp}]</span>{' '}
            <span style={{ color: '#9ca3af' }}>{log.level}</span> - {log.message}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DebugPanel;

import React from 'react';
import { getUserFriendlyError } from '../utils/errors';

interface ErrorScreenProps {
  error: string;
  onRetry: () => void;
  onReset: () => void;
}

const ErrorScreen: React.FC<ErrorScreenProps> = ({ error, onRetry, onReset }) => {
  const friendlyError = getUserFriendlyError(new Error(error));

  return (
    <div
      style={{
        maxWidth: '500px',
        padding: '3rem 2rem',
        textAlign: 'center',
        backgroundColor: 'var(--bg-primary)',
        borderRadius: '1rem',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>❌</div>
      <h2 style={{ marginBottom: '1rem', color: 'var(--danger)' }}>Something went wrong</h2>

      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          padding: '1.5rem',
          borderRadius: '0.5rem',
          marginBottom: '2rem',
          textAlign: 'left',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          color: 'var(--text-secondary)',
          fontSize: '0.9rem',
          fontFamily: 'monospace',
        }}
      >
        {friendlyError}
      </div>

      <div style={{ display: 'flex', gap: '1rem' }}>
        <button
          onClick={onRetry}
          style={{
            flex: 1,
            backgroundColor: 'var(--primary)',
            color: 'white',
          }}
        >
          Try Again
        </button>
        <button
          onClick={onReset}
          style={{
            flex: 1,
            backgroundColor: 'var(--bg-secondary)',
          }}
        >
          Start Over
        </button>
      </div>
    </div>
  );
};

export default ErrorScreen;

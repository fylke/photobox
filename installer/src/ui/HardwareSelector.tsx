import React from 'react';
import { PI_MODELS, PiModel } from '../config';

interface HardwareSelectorProps {
  onSelect: (model: PiModel) => void;
}

const HardwareSelector: React.FC<HardwareSelectorProps> = ({ onSelect }) => {
  return (
    <div
      style={{
        maxWidth: '900px',
        padding: '3rem 2rem',
        backgroundColor: 'var(--bg-primary)',
        borderRadius: '1rem',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <h2 style={{ marginBottom: '0.5rem' }}>Which Raspberry Pi?</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
        Select your Raspberry Pi model to see the required SD card size
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        {(Object.keys(PI_MODELS) as PiModel[]).map((model) => {
          const config = PI_MODELS[model];
          return (
            <button
              key={model}
              onClick={() => onSelect(model)}
              style={{
                padding: '1.5rem',
                textAlign: 'left',
                backgroundColor: 'var(--bg-secondary)',
                border: '2px solid var(--border)',
                borderRadius: '0.75rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--primary)';
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  'var(--bg-tertiary)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)';
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  'var(--bg-secondary)';
              }}
            >
              <div style={{ fontSize: '1.3rem', fontWeight: '600', marginBottom: '0.5rem' }}>
                {config.name}
              </div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                {config.specs}
              </div>
              <div style={{ marginTop: '1rem', color: 'var(--primary)', fontWeight: '600' }}>
                Image: {config.imageSizeGB} GB
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Needs {config.minSDCardGB} GB+ SD card
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default HardwareSelector;

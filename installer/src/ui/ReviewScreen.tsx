import React, { useState } from 'react';
import { PiModel, CountryConfig, PI_MODELS } from '../config';

interface ReviewScreenProps {
  piModel: PiModel;
  country: CountryConfig;
  debugMode: boolean;
  onToggleDebug: (enabled: boolean) => void;
  onStart: () => void;
  onBack: () => void;
}

const ReviewScreen: React.FC<ReviewScreenProps> = ({
  piModel,
  country,
  debugMode,
  onToggleDebug,
  onStart,
  onBack,
}) => {
  const [confirmed, setConfirmed] = useState(false);
  const config = PI_MODELS[piModel];

  return (
    <div
      style={{
        maxWidth: '500px',
        padding: '2rem',
        backgroundColor: 'var(--bg-primary)',
        borderRadius: '1rem',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <h2 style={{ marginBottom: '1rem' }}>Review Your Settings</h2>

      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          padding: '1.5rem',
          borderRadius: '0.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Raspberry Pi</div>
          <div style={{ fontSize: '1.1rem', fontWeight: '600' }}>{config.name}</div>
        </div>
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Image Size</div>
          <div style={{ fontSize: '1.1rem', fontWeight: '600' }}>{config.imageSizeGB} GB</div>
        </div>
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            WiFi Country
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: '600' }}>
            {country.name} ({country.domain})
          </div>
        </div>
      </div>

      <div
        style={{
          backgroundColor: 'var(--danger)',
          color: 'white',
          padding: '1rem',
          borderRadius: '0.5rem',
          marginBottom: '1.5rem',
          fontSize: '0.9rem',
        }}
      >
        ⚠️ <strong>All data on the SD card will be erased!</strong> Make sure you have the correct
        device.
      </div>

      <label style={{ display: 'flex', alignItems: 'center', marginBottom: '1rem', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          style={{ marginRight: '0.5rem', width: 'auto' }}
        />
        <span>I understand and confirm</span>
      </label>

      <label style={{ display: 'flex', alignItems: 'center', marginBottom: '1.5rem', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={debugMode}
          onChange={(e) => onToggleDebug(e.target.checked)}
          style={{ marginRight: '0.5rem', width: 'auto' }}
        />
        <span style={{ fontSize: '0.9rem' }}>Enable debug logging</span>
      </label>

      <div style={{ display: 'flex', gap: '1rem' }}>
        <button onClick={onBack} style={{ flex: 1, backgroundColor: 'var(--bg-secondary)' }}>
          ← Back
        </button>
        <button
          onClick={onStart}
          disabled={!confirmed}
          style={{
            flex: 1,
            backgroundColor: confirmed ? 'var(--primary)' : 'var(--text-secondary)',
            color: 'white',
          }}
        >
          Start Writing →
        </button>
      </div>
    </div>
  );
};

export default ReviewScreen;

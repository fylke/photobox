import React from 'react';
import { PiModel, PI_MODELS } from '../config';

interface SuccessScreenProps {
  piModel: PiModel;
  onReset: () => void;
}

const SuccessScreen: React.FC<SuccessScreenProps> = ({ piModel, onReset }) => {
  const config = PI_MODELS[piModel];

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
      <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>✅</div>
      <h2 style={{ marginBottom: '1rem' }}>Success!</h2>
      <p style={{ fontSize: '1.1rem', marginBottom: '2rem', color: 'var(--text-secondary)' }}>
        Your SD card is ready for the {config.name}
      </p>

      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          padding: '1.5rem',
          borderRadius: '0.5rem',
          marginBottom: '2rem',
          textAlign: 'left',
        }}
      >
        <h3 style={{ marginBottom: '1rem' }}>Next steps:</h3>
        <ol style={{ paddingLeft: '1.5rem', color: 'var(--text-secondary)' }}>
          <li style={{ marginBottom: '0.5rem' }}>Safely eject the SD card from your computer</li>
          <li style={{ marginBottom: '0.5rem' }}>Insert it into your Raspberry Pi</li>
          <li style={{ marginBottom: '0.5rem' }}>Connect the camera (if available)</li>
          <li>Power on the Pi and wait for the setup network to appear</li>
        </ol>
      </div>

      <button
        onClick={onReset}
        style={{
          backgroundColor: 'var(--primary)',
          color: 'white',
          padding: '1rem 2rem',
          fontSize: '1rem',
          fontWeight: '600',
        }}
      >
        Write Another Card
      </button>
    </div>
  );
};

export default SuccessScreen;

import React from 'react';

interface SplashScreenProps {
  onNext: () => void;
}

const SplashScreen: React.FC<SplashScreenProps> = ({ onNext }) => {
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
      <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem', color: 'var(--primary)' }}>
        📷 Photobox Imager
      </h1>
      <p style={{ fontSize: '1.1rem', color: 'var(--text-secondary)', marginBottom: '2rem' }}>
        Write Photobox to your Raspberry Pi SD card
      </p>
      <p style={{ marginBottom: '2rem', color: 'var(--text-secondary)' }}>
        Takes just a few minutes. No installation required.
      </p>
      <button
        onClick={onNext}
        style={{
          backgroundColor: 'var(--primary)',
          color: 'white',
          padding: '1rem 2rem',
          fontSize: '1.1rem',
          fontWeight: '600',
        }}
      >
        Get Started →
      </button>
    </div>
  );
};

export default SplashScreen;

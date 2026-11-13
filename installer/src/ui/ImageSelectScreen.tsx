import React, { useRef, useState } from 'react';
import { PiModel, CountryConfig, PI_MODELS } from '../config';
import { logger } from '../utils/logger';

interface ImageSelectScreenProps {
  piModel: PiModel;
  country: CountryConfig & { code: string };
  onImageSelected: (file: File) => void;
  onBack: () => void;
}

const ImageSelectScreen: React.FC<ImageSelectScreenProps> = ({
  piModel,
  country,
  onImageSelected,
  onBack,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const config = PI_MODELS[piModel];

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.img.xz')) {
      logger.error('Invalid file type', { name: file.name });
      alert('Please select a .img.xz file');
      return;
    }

    setSelectedFile(file);
    logger.info('Image file selected', { name: file.name, size: file.size });
  };

  const handleContinue = () => {
    if (!selectedFile) {
      alert('Please select an image file');
      return;
    }
    onImageSelected(selectedFile);
  };

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
      <h2 style={{ marginBottom: '1rem' }}>Select Image File</h2>

      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          padding: '1.5rem',
          borderRadius: '0.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Raspberry Pi
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: '600' }}>{config.name}</div>
        </div>
        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            WiFi Country
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: '600' }}>
            {country.name} ({country.code})
          </div>
        </div>
      </div>

      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          padding: '2rem',
          borderRadius: '0.5rem',
          marginBottom: '1.5rem',
          textAlign: 'center',
          border: '2px dashed var(--text-secondary)',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)';
        }}
        onDragLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--bg-secondary)';
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.currentTarget.style.backgroundColor = 'var(--bg-secondary)';
          const file = e.dataTransfer.files?.[0];
          if (file) {
            handleFileChange({ target: { files: e.dataTransfer.files } } as any);
          }
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".img.xz"
          onChange={handleFileChange}
          style={{ display: 'none' }}
        />
        <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>📁</div>
        <div style={{ fontWeight: '600', marginBottom: '0.5rem' }}>
          {selectedFile ? selectedFile.name : 'Click or drag image file here'}
        </div>
        {selectedFile && (
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {(selectedFile.size / (1024 * 1024 * 1024)).toFixed(2)} GB
          </div>
        )}
        <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.5rem' }}>
          Expected format: <strong>.img.xz</strong>
        </div>
      </div>

      <div
        style={{
          backgroundColor: 'var(--info)',
          color: 'var(--text-primary)',
          padding: '1rem',
          borderRadius: '0.5rem',
          marginBottom: '1.5rem',
          fontSize: '0.9rem',
        }}
      >
        <strong>How to get the image:</strong>
        <ol style={{ marginTop: '0.5rem', marginBottom: 0, paddingLeft: '1.5rem' }}>
          <li>Go to the latest release at https://github.com/fylke/photobox/releases</li>
          <li>Download the <code style={{ backgroundColor: 'rgba(0,0,0,0.1)', padding: '0.2rem 0.4rem', borderRadius: '0.25rem' }}>image_*.img.xz</code> file</li>
          <li>Come back here and select it</li>
        </ol>
      </div>

      <div style={{ display: 'flex', gap: '1rem' }}>
        <button onClick={onBack} style={{ flex: 1, backgroundColor: 'var(--bg-secondary)' }}>
          ← Back
        </button>
        <button
          onClick={handleContinue}
          disabled={!selectedFile}
          style={{
            flex: 1,
            backgroundColor: selectedFile ? 'var(--primary)' : 'var(--text-secondary)',
            color: 'white',
          }}
        >
          Continue →
        </button>
      </div>
    </div>
  );
};

export default ImageSelectScreen;

import React, { useEffect, useState } from 'react';
import { PiModel, CountryConfig, PI_MODELS } from '../config';
import { logger } from '../utils/logger';
import { imageDownloader } from '../imaging/imageDownloader';
import { imageProcessor } from '../imaging/imageProcessor';
import { imageWriter } from '../webusb/writer';
import { formatBytes, formatSpeed, formatETA, calculateETA } from '../utils/format';
import DebugPanel from './DebugPanel';

type Stage = 'downloading' | 'customizing' | 'writing' | 'complete';

interface ProgressScreenProps {
  piModel: PiModel;
  country: CountryConfig;
  debugMode: boolean;
  onComplete: () => void;
  onError: (error: string) => void;
}

const ProgressScreen: React.FC<ProgressScreenProps> = ({
  piModel,
  country,
  debugMode,
  onComplete,
  onError,
}) => {
  const [stage, setStage] = useState<Stage>('downloading');
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [eta, setEta] = useState('');
  const [speed, setSpeed] = useState('');
  const config = PI_MODELS[piModel];

  useEffect(() => {
    let cancelled = false;

    const runProcess = async () => {
      try {
        logger.info('Starting write process', { piModel, country: country.domain });

        setStatusText(`Downloading Photobox image (${config.imageSizeGB} GB)...`);
        setStage('downloading');

        const imageData = await imageDownloader.downloadImage(piModel, (downloaded, total) => {
          if (cancelled) return;

          const percent = Math.round((downloaded / total) * 100);
          setProgress(percent);

          const bytesPerSecond = downloaded / ((Date.now() - Date.now() + 1000) / 1000);
          const remaining = total - downloaded;
          const etaSeconds = calculateETA(remaining, bytesPerSecond);

          setSpeed(formatSpeed(bytesPerSecond));
          setEta(formatETA(etaSeconds));
          setStatusText(
            `Downloaded ${formatBytes(downloaded)} / ${formatBytes(total)} (${percent}%)`
          );
        });

        if (cancelled) return;

        logger.info('Download complete, customizing image');
        setStage('customizing');
        setStatusText('Customizing image with WiFi settings...');
        setProgress(0);
        setEta('');
        setSpeed('');

        const customizedImage = await imageProcessor.injectWiFiDomain(
          imageData,
          country.domain
        );

        if (cancelled) return;

        logger.info('Image customized, starting write');
        setStage('writing');
        setStatusText('Writing to SD card...');
        setProgress(0);

        await imageWriter.writeImage(customizedImage, (progress) => {
          if (cancelled) return;

          const percent = Math.round((progress.bytesWritten / progress.totalBytes) * 100);
          setProgress(percent);

          const remaining = progress.totalBytes - progress.bytesWritten;
          const etaSeconds = calculateETA(remaining, progress.bytesPerSecond);

          setSpeed(formatSpeed(progress.bytesPerSecond));
          setEta(formatETA(etaSeconds));
          setStatusText(
            `Written ${formatBytes(progress.bytesWritten)} / ${formatBytes(progress.totalBytes)} (${percent}%)`
          );
        });

        if (cancelled) return;

        logger.info('Write complete');
        setStage('complete');
        setStatusText('Complete! Ready to use.');
        setProgress(100);
        setEta('');
        setSpeed('');

        setTimeout(onComplete, 1000);
      } catch (error) {
        if (cancelled) return;

        const message = error instanceof Error ? error.message : String(error);
        logger.error('Process failed', { error: message });
        onError(message);
      }
    };

    runProcess();

    return () => {
      cancelled = true;
    };
  }, [piModel, country, config.imageSizeGB, onComplete, onError]);

  return (
    <div
      style={{
        maxWidth: debugMode ? '1200px' : '500px',
        padding: '2rem',
        backgroundColor: 'var(--bg-primary)',
        borderRadius: '1rem',
        boxShadow: 'var(--shadow-lg)',
        display: 'flex',
        gap: '2rem',
      }}
    >
      <div style={{ flex: debugMode ? 1 : 'none', minWidth: 0 }}>
        <h2 style={{ marginBottom: '0.5rem' }}>Writing Image</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
          {stage === 'downloading' && '⬇️ Downloading image...'}
          {stage === 'customizing' && '⚙️ Customizing image...'}
          {stage === 'writing' && '💾 Writing to SD card...'}
          {stage === 'complete' && '✅ Complete!'}
        </p>

        <div
          style={{
            backgroundColor: 'var(--bg-secondary)',
            padding: '1.5rem',
            borderRadius: '0.5rem',
            marginBottom: '1.5rem',
          }}
        >
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
              {statusText}
            </div>
            <div
              style={{
                width: '100%',
                height: '8px',
                backgroundColor: 'var(--bg-tertiary)',
                borderRadius: '4px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${progress}%`,
                  backgroundColor: stage === 'complete' ? 'var(--success)' : 'var(--primary)',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '1rem',
              fontSize: '0.9rem',
            }}
          >
            {speed && (
              <div>
                <div style={{ color: 'var(--text-secondary)' }}>Speed</div>
                <div style={{ fontWeight: '600' }}>{speed}</div>
              </div>
            )}
            {eta && (
              <div>
                <div style={{ color: 'var(--text-secondary)' }}>Estimated time</div>
                <div style={{ fontWeight: '600' }}>{eta}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {debugMode && <DebugPanel />}
    </div>
  );
};

export default ProgressScreen;

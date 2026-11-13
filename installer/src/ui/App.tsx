import React, { useCallback, useState } from 'react';
import '../styles/global.css';
import { PiModel, CountryConfig } from '../config';
import { logger } from '../utils/logger';
import SplashScreen from './SplashScreen';
import HardwareSelector from './HardwareSelector';
import CountryPicker from './CountryPicker';
import ImageSelectScreen from './ImageSelectScreen';
import ReviewScreen from './ReviewScreen';
import ProgressScreen from './ProgressScreen';
import SuccessScreen from './SuccessScreen';
import ErrorScreen from './ErrorScreen';

export type Screen =
  | 'splash'
  | 'hardware'
  | 'country'
  | 'image-select'
  | 'review'
  | 'progress'
  | 'success'
  | 'error';

export interface AppState {
  piModel: PiModel | null;
  country: (CountryConfig & { code: string }) | null;
  imageFile: File | null;
  debugMode: boolean;
  error: string | null;
}

const App: React.FC = () => {
  const [screen, setScreen] = useState<Screen>('splash');
  const [state, setState] = useState<AppState>({
    piModel: null,
    country: null,
    imageFile: null,
    debugMode: logger.isDebugEnabled(),
    error: null,
  });

  const handleSelectPi = useCallback((model: PiModel) => {
    logger.info('Selected Pi model', { model });
    setState((prev) => ({ ...prev, piModel: model }));
    setScreen('country');
  }, []);

  const handleSelectCountry = useCallback((country: CountryConfig & { code: string }) => {
    logger.info('Selected country', { country: country.code, domain: country.domain });
    setState((prev) => ({ ...prev, country }));
    setScreen('image-select');
  }, []);

  const handleSelectImage = useCallback((imageFile: File) => {
    logger.info('Selected image file', { name: imageFile.name, size: imageFile.size });
    setState((prev) => ({ ...prev, imageFile }));
    setScreen('review');
  }, []);

  const handleToggleDebug = useCallback((enabled: boolean) => {
    logger.setDebugMode(enabled);
    setState((prev) => ({ ...prev, debugMode: enabled }));
  }, []);

  const handleStartWrite = useCallback(() => {
    setScreen('progress');
  }, []);

  const handleWriteComplete = useCallback(() => {
    setScreen('success');
  }, []);

  const handleError = useCallback((error: string) => {
    logger.error('Application error', { error });
    setState((prev) => ({ ...prev, error }));
    setScreen('error');
  }, []);

  const handleRetry = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
    setScreen('review');
  }, []);

  const handleReset = useCallback(() => {
    setState({
      piModel: null,
      country: null,
      imageFile: null,
      debugMode: logger.isDebugEnabled(),
      error: null,
    });
    setScreen('splash');
    logger.clearLogs();
  }, []);

  const renderScreen = () => {
    switch (screen) {
      case 'splash':
        return <SplashScreen onNext={() => setScreen('hardware')} />;

      case 'hardware':
        return <HardwareSelector onSelect={handleSelectPi} />;

      case 'country':
        return (
          state.piModel && (
            <CountryPicker
              onSelect={handleSelectCountry}
              onBack={() => setScreen('hardware')}
            />
          )
        );

      case 'image-select':
        return (
          state.piModel &&
          state.country && (
            <ImageSelectScreen
              piModel={state.piModel}
              country={state.country}
              onImageSelected={handleSelectImage}
              onBack={() => setScreen('country')}
            />
          )
        );

      case 'review':
        return (
          state.piModel &&
          state.country &&
          state.imageFile && (
            <ReviewScreen
              piModel={state.piModel}
              country={state.country}
              debugMode={state.debugMode}
              onToggleDebug={handleToggleDebug}
              onStart={handleStartWrite}
              onBack={() => setScreen('image-select')}
            />
          )
        );

      case 'progress':
        return (
          state.piModel &&
          state.country &&
          state.imageFile && (
            <ProgressScreen
              piModel={state.piModel}
              country={state.country}
              imageFile={state.imageFile}
              debugMode={state.debugMode}
              onComplete={handleWriteComplete}
              onError={handleError}
            />
          )
        );

      case 'success':
        return <SuccessScreen piModel={state.piModel!} onReset={handleReset} />;

      case 'error':
        return (
          <ErrorScreen error={state.error!} onRetry={handleRetry} onReset={handleReset} />
        );

      default:
        return null;
    }
  };

  return <div style={{ width: '100%' }}>{renderScreen()}</div>;
};

export default App;

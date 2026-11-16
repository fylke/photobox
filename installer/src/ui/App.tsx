import React, { useEffect, useState } from 'react';
import '../styles/global.css';
import { getCountriesByName } from '../config';
import { chooseImageDestination, getImageManifest, prepareImage } from '../imaging/prepareImage';

const App: React.FC = () => {
  const [country, setCountry] = useState('');
  const [debug, setDebug] = useState(false);
  const [manifest, setManifest] = useState<Awaited<ReturnType<typeof getImageManifest>> | null>(null);
  const [status, setStatus] = useState('Checking for an image...');
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let active = true;
    getImageManifest().then(
      (result) => {
        if (active) {
          setManifest(result);
          setStatus('');
        }
      },
      (reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason));
          setStatus('');
        }
      },
    );
    return () => { active = false; };
  }, []);

  const handlePrepare = async () => {
    if (!manifest || !country || working) return;
    setError('');
    setStatus('');
    setWorking(true);
    try {
      const destination = await chooseImageDestination();
      await prepareImage(destination, manifest, country, debug, setStatus);
      setStatus('Image saved. Write it to your SD card with Raspberry Pi Imager using “Use custom”.');
    } catch (reason) {
      if (reason instanceof Error && reason.name === 'AbortError') {
        setStatus('Image preparation cancelled.');
      } else if (reason instanceof Error && reason.name === 'QuotaExceededError') {
        setError('Browser temporary storage is full. Use a regular (not private) browser window and free disk space, then try again.');
      } else {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      setWorking(false);
    }
  };

  return (
    <main style={{ maxWidth: '600px', padding: '2rem', background: 'var(--bg-primary)', borderRadius: '1rem', boxShadow: 'var(--shadow-lg)' }}>
      <h1 style={{ marginBottom: '1rem', color: 'var(--primary)' }}>Photobox image</h1>
      <p style={{ marginBottom: '1rem' }}>
        Prepare an image for a Raspberry Pi 4 or 5, then write it with Raspberry Pi Imager.
      </p>
      <label htmlFor="country" style={{ display: 'block', marginBottom: '0.5rem' }}>Wi-Fi country</label>
      <select id="country" value={country} onChange={(event) => setCountry(event.target.value)} disabled={working}>
        <option value="">Select the country where the Pi will be used</option>
        {getCountriesByName().map(([code, details]) => (
          <option value={code} key={code}>{details.name} ({code})</option>
        ))}
      </select>
      <label style={{ display: 'flex', alignItems: 'start', gap: '0.5rem', marginTop: '1.5rem' }}>
        <input
          type="checkbox"
          checked={debug}
          disabled={working || !manifest?.bootDebug}
          onChange={(event) => setDebug(event.target.checked)}
          style={{ width: 'auto', marginTop: '0.3rem' }}
        />
        <span>
          Enable Raspberry Pi boot debug on every boot. Logs appear on the console where available
          and are saved on the SD card’s boot partition, up to 200 MiB. They may contain sensitive
          information and can be read by anyone with the card.
        </span>
      </label>
      {manifest && !manifest.bootDebug && (
        <p style={{ marginTop: '0.5rem' }}>This release does not support boot debug; a newer image is required.</p>
      )}
      <p style={{ margin: '1.5rem 0', color: 'var(--text-secondary)' }}>
        The browser downloads and prepares the base image locally. Allow several gigabytes of free
        disk space, keep this page open, and choose where to save the resulting uncompressed image.
      </p>
      <button
        onClick={handlePrepare}
        disabled={!manifest || !country || working}
        style={{ width: '100%', background: 'var(--primary)', color: 'white' }}
      >
        {working ? 'Preparing image...' : 'Prepare and save image'}
      </button>
      {status && <p role="status" style={{ marginTop: '1rem' }}>{status}</p>}
      {error && <p role="alert" style={{ marginTop: '1rem', color: 'var(--danger)' }}>{error}</p>}
      <p style={{ marginTop: '1.5rem', color: 'var(--text-secondary)' }}>
        Writing the image erases the selected SD card. The image and first-boot setup have not yet
        been validated on physical hardware.
      </p>
    </main>
  );
};

export default App;

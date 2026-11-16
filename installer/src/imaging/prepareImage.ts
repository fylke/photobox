import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from '@noble/hashes/utils';
import { XzReadableStream } from 'xz-decompress';
import { customizeBoot } from './bootConfig';

interface ImageManifest {
  sha256: string;
  size: number;
  bootDebug: boolean;
}

declare global {
  interface Window {
    showSaveFilePicker?: (options: {
      suggestedName: string;
      types: { description: string; accept: Record<string, string[]> }[];
    }) => Promise<FileSystemFileHandle>;
  }
}

export async function getImageManifest(): Promise<ImageManifest> {
  const response = await fetch(`${import.meta.env.BASE_URL}image/manifest.json`, { cache: 'no-store' });
  if (!response.ok) throw new Error('No base image is available for this installer');
  const manifest: unknown = await response.json();
  if (
    typeof manifest !== 'object' ||
    manifest === null ||
    !('sha256' in manifest) ||
    typeof manifest.sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(manifest.sha256) ||
    !('size' in manifest) ||
    typeof manifest.size !== 'number' ||
    !Number.isSafeInteger(manifest.size) ||
    manifest.size <= 0 ||
    !('bootDebug' in manifest) ||
    typeof manifest.bootDebug !== 'boolean'
  ) {
    throw new Error('Invalid base image metadata');
  }
  return { sha256: manifest.sha256, size: manifest.size, bootDebug: manifest.bootDebug };
}

export function chooseImageDestination(): Promise<FileSystemFileHandle> {
  if (!window.showSaveFilePicker || !navigator.storage?.getDirectory) {
    throw new Error('This browser cannot prepare images. Use a current Chrome or Edge browser.');
  }
  return window.showSaveFilePicker({
    suggestedName: 'photobox-configured.img',
    types: [{ description: 'Raspberry Pi disk image', accept: { 'application/octet-stream': ['.img'] } }],
  });
}

export async function prepareImage(
  destination: FileSystemFileHandle,
  manifest: ImageManifest,
  country: string,
  debug: boolean,
  onProgress: (message: string) => void,
): Promise<void> {
  if (debug && !manifest.bootDebug) {
    throw new Error('This release does not support boot debug. Wait for a newer image.');
  }
  const directory = await navigator.storage.getDirectory();
  const temporaryName = `photobox-${crypto.randomUUID()}.img`;
  const temporary = await directory.getFileHandle(temporaryName, { create: true });
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}image/base.img.xz`, { cache: 'no-store' });
    if (!response.ok || !response.body) throw new Error('Failed to download the base image');

    const hash = sha256.create();
    let downloaded = 0;
    let lastUpdate = 0;
    const compressed = response.body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          hash.update(chunk);
          downloaded += chunk.length;
          if (Date.now() - lastUpdate > 250) {
            onProgress(`Downloading base image: ${Math.min(100, Math.floor(downloaded * 100 / manifest.size))}%`);
            lastUpdate = Date.now();
          }
          controller.enqueue(chunk);
        },
      }),
    );
    const source = new XzReadableStream(compressed).getReader();
    const temporaryOutput = await temporary.createWritable();
    try {
      while (true) {
        const { done, value } = await source.read();
        if (done) break;
        await temporaryOutput.write(new Uint8Array(value));
      }
      if (downloaded !== manifest.size || bytesToHex(hash.digest()) !== manifest.sha256) {
        throw new Error('Base image checksum mismatch');
      }
      await temporaryOutput.close();
    } catch (error) {
      await source.cancel();
      await temporaryOutput.abort();
      throw error;
    } finally {
      source.releaseLock();
    }

    onProgress('Applying Wi-Fi and boot settings...');
    await customizeBoot(temporary, country, debug);

    onProgress('Saving the configured image...');
    const image = await temporary.getFile();
    const output = await destination.createWritable();
    await image.stream().pipeTo(output);
  } finally {
    await directory.removeEntry(temporaryName);
  }
}

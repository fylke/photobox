import { logger } from '../utils/logger';
import { PI_MODELS, PiModel } from '../config';

const GITHUB_RELEASE_VERSION = 'v0.0.1-rc.1';

// Cache for discovered image filename
let discoveredImageName: string | null = null;

async function discoverImageName(): Promise<string> {
  if (discoveredImageName) return discoveredImageName;

  try {
    // Query GitHub API to find the actual image filename
    const apiUrl = `https://api.github.com/repos/fylke/photobox/releases/tags/${GITHUB_RELEASE_VERSION}`;
    const response = await fetch(apiUrl);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch release info: ${response.status}`);
    }

    const release = await response.json() as { assets: Array<{ name: string }> };
    const imageAsset = release.assets.find((a: { name: string }) => 
      a.name.endsWith('.img.xz') && !a.name.includes('QEMU')
    );
    
    if (!imageAsset) {
      throw new Error('No image found in release');
    }

    discoveredImageName = imageAsset.name;
    logger.info('Discovered image name', { name: discoveredImageName });
    return discoveredImageName;
  } catch (error) {
    logger.error('Failed to discover image name', error);
    throw new Error(`Could not discover image: ${String(error)}`);
  }
}

class ImageDownloader {
  private imageCache = new Map<string, ArrayBuffer>();

  async downloadImage(
    piModel: PiModel,
    onProgress?: (downloaded: number, total: number) => void
  ): Promise<ArrayBuffer> {
    const cacheKey = piModel;

    if (this.imageCache.has(cacheKey)) {
      logger.info('Using cached image', { model: piModel });
      return this.imageCache.get(cacheKey)!;
    }

    logger.info('Starting image download', { model: piModel });

    try {
      const imageSize = PI_MODELS[piModel].imageSizeBytes;
      const imageName = await discoverImageName();

      // Direct GitHub release download URL
      const url = `https://github.com/fylke/photobox/releases/download/${GITHUB_RELEASE_VERSION}/${imageName}`;

      logger.debug('Downloading from GitHub releases', { url, size: imageSize });

      // Use no-cors mode to bypass CORS, but this won't give us the blob directly
      // Instead, we need to stream the response and convert it to ArrayBuffer
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'application/octet-stream',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to download: ${response.status} ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('Response body is empty');
      }

      // Read the response body as a stream
      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let downloaded = 0;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          chunks.push(value);
          downloaded += value.length;

          if (onProgress) {
            onProgress(downloaded, imageSize);
          }
        }
      } finally {
        reader.releaseLock();
      }

      // Combine chunks into single buffer
      const result = new Uint8Array(downloaded);
      let offset = 0;
      for (const chunk of chunks) {
        result.set(chunk, offset);
        offset += chunk.length;
      }

      const imageData = result.buffer;

      logger.info('Image download complete', {
        size: imageData.byteLength,
        model: piModel,
      });

      this.imageCache.set(cacheKey, imageData);
      return imageData;
    } catch (error) {
      logger.error('Download failed', error);
      throw new Error(`Download failed: ${String(error)}`);
    }
  }

  clearCache(): void {
    this.imageCache.clear();
    logger.info('Image cache cleared');
  }

  getCacheInfo(): { size: number; items: number } {
    let totalSize = 0;
    for (const [, buffer] of this.imageCache) {
      totalSize += buffer.byteLength;
    }
    return {
      size: totalSize,
      items: this.imageCache.size,
    };
  }
}

export const imageDownloader = new ImageDownloader();

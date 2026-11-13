import { logger } from '../utils/logger';
import { downloadFile } from '../utils/format';
import { PI_MODELS, PiModel } from '../config';

const GITHUB_RELEASE_VERSION = 'v0.0.1-rc.1';
const CORS_PROXY = 'https://cors.isomorphic-git.org';

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
    const imageAsset = release.assets.find((a: { name: string }) => a.name.endsWith('.img.xz') && !a.name.includes('QEMU'));
    
    if (!imageAsset) {
      throw new Error('No image found in release');
    }

    discoveredImageName = imageAsset.name;
    logger.info('Discovered image name', { name: discoveredImageName });
    return discoveredImageName;
  } catch (error) {
    logger.error('Failed to discover image name', error);
    throw new Error(`Could not discover image filename: ${String(error)}`);
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

      const directUrl = `https://github.com/fylke/photobox/releases/download/${GITHUB_RELEASE_VERSION}/${imageName}`;
      // Use CORS proxy to bypass GitHub's lack of CORS headers
      const url = `${CORS_PROXY}/${directUrl}`;

      logger.debug('Downloading from URL', { url, size: imageSize });

      const imageData = await downloadFile(url, onProgress);

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

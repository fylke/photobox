import { logger } from '../utils/logger';
import { downloadFile } from '../utils/format';
import { PI_MODELS, PiModel } from '../config';

const GITHUB_RELEASE_VERSION = 'v0.0.1-rc.1';

// Cache for discovered image info
let discoveredImageInfo: { assetId: number; name: string } | null = null;

async function discoverImageAsset(): Promise<{ assetId: number; name: string }> {
  if (discoveredImageInfo) return discoveredImageInfo;

  try {
    // Query GitHub API to find the actual image asset
    const apiUrl = `https://api.github.com/repos/fylke/photobox/releases/tags/${GITHUB_RELEASE_VERSION}`;
    const response = await fetch(apiUrl);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch release info: ${response.status}`);
    }

    const release = await response.json() as { assets: Array<{ id: number; name: string }> };
    const imageAsset = release.assets.find((a: { id: number; name: string }) => 
      a.name.endsWith('.img.xz') && !a.name.includes('QEMU')
    );
    
    if (!imageAsset) {
      throw new Error('No image found in release');
    }

    discoveredImageInfo = { assetId: imageAsset.id, name: imageAsset.name };
    logger.info('Discovered image asset', discoveredImageInfo);
    return discoveredImageInfo;
  } catch (error) {
    logger.error('Failed to discover image asset', error);
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
      const { assetId, name } = await discoverImageAsset();

      // Use GitHub API asset download endpoint
      // This endpoint returns a redirect that works from browsers
      const url = `https://api.github.com/repos/fylke/photobox/releases/assets/${assetId}`;

      logger.debug('Downloading from GitHub API', { url, assetId, name, size: imageSize });

      // Fetch with Accept header to get the download redirect
      const response = await fetch(url, {
        headers: {
          'Accept': 'application/octet-stream',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to download: ${response.status} ${response.statusText}`);
      }

      const imageData = await downloadFile(response.url, onProgress);

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

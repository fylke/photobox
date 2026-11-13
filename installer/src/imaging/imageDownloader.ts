import { logger } from '../utils/logger';
import { downloadFile } from '../utils/format';
import { PI_MODELS, PiModel } from '../config';

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
      const imageName = PI_MODELS[piModel].imageName;
      const imageSize = PI_MODELS[piModel].imageSizeBytes;

      const url = `https://github.com/fylke/photobox/releases/download/latest/${imageName}`;

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

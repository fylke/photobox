import { logger } from '../utils/logger';
import { createError } from '../utils/errors';

export interface WriteProgress {
  bytesWritten: number;
  totalBytes: number;
  bytesPerSecond: number;
}

const CHUNK_SIZE = 4 * 1024 * 1024;

class ImageWriter {
  async writeImage(
    imageData: ArrayBuffer,
    onProgress?: (progress: WriteProgress) => void
  ): Promise<void> {
    logger.info('Image write requested', { size: imageData.byteLength });

    try {
      if (!('usb' in navigator)) {
        throw createError('WEBUSB_NOT_SUPPORTED');
      }

      const devices = await (navigator as any).usb.getDevices();
      if (devices.length === 0) {
        throw createError('NO_DEVICE_FOUND');
      }

      const device = devices[0];
      logger.debug('Writing to device', {
        vendorId: device.vendorId,
        productId: device.productId,
      });

      let startTime = Date.now();
      let lastProgressTime = startTime;
      let bytesWritten = 0;
      const imageBuffer = new Uint8Array(imageData);

      while (bytesWritten < imageBuffer.length) {
        const chunkEnd = Math.min(bytesWritten + CHUNK_SIZE, imageBuffer.length);
        const chunk = imageBuffer.slice(bytesWritten, chunkEnd);

        await this.writeChunk(device, chunk);
        bytesWritten = chunkEnd;

        const now = Date.now();
        if (now - lastProgressTime > 500 || bytesWritten === imageBuffer.length) {
          const elapsedSeconds = (now - startTime) / 1000;
          const bytesPerSecond = bytesWritten / elapsedSeconds;

          if (onProgress) {
            onProgress({
              bytesWritten,
              totalBytes: imageBuffer.length,
              bytesPerSecond,
            });
          }

          lastProgressTime = now;
          logger.debug('Write progress', {
            progress: Math.round((bytesWritten / imageBuffer.length) * 100) + '%',
            bytesWritten,
            speed: Math.round(bytesPerSecond / 1024 / 1024) + ' MB/s',
          });
        }
      }

      logger.info('Image write complete');
    } catch (error) {
      logger.error('Write failed', error);
      if (error instanceof Error) {
        throw createError('WRITE_FAILED', error.message);
      }
      throw error;
    }
  }

  private async writeChunk(device: any, chunk: Uint8Array): Promise<void> {
    try {
      await device.transferOut(1, chunk);
    } catch (error) {
      logger.error('Chunk write failed', error);
      throw error;
    }
  }
}

export const imageWriter = new ImageWriter();

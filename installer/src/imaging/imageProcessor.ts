import { logger } from '../utils/logger';

class ImageProcessor {
  private stringToUint8Array(str: string): Uint8Array {
    const arr = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i++) {
      arr[i] = str.charCodeAt(i);
    }
    return arr;
  }

  async injectWiFiDomain(imageData: ArrayBuffer, wifiDomain: string): Promise<ArrayBuffer> {
    logger.info('Injecting WiFi domain into image', { domain: wifiDomain });

    try {
      const image = new Uint8Array(imageData);

      logger.debug('Image size before injection', { bytes: image.length });

      const injectionMarker = this.stringToUint8Array('PHOTOBOX_WIFI_DOMAIN=');
      const replacement = `PHOTOBOX_WIFI_DOMAIN=${wifiDomain}`.padEnd(50, '\x00');
      const replacementBytes = this.stringToUint8Array(replacement);

      let injected = false;
      for (let i = 0; i < image.length - injectionMarker.length; i++) {
        if (image.slice(i, i + injectionMarker.length).every((v, j) => v === injectionMarker[j])) {
          for (let j = 0; j < replacementBytes.length; j++) {
            image[i + j] = replacementBytes[j];
          }
          injected = true;
          logger.debug('WiFi domain injected at offset', { offset: i });
          break;
        }
      }

      if (!injected) {
        logger.warn('WiFi domain injection marker not found, proceeding with default');
      }

      logger.info('WiFi domain injection complete');
      return image.buffer;
    } catch (error) {
      logger.error('WiFi domain injection failed', error);
      throw error;
    }
  }
}

export const imageProcessor = new ImageProcessor();

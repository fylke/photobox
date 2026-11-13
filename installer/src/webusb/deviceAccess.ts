import { logger } from '../utils/logger';
import { createError } from '../utils/errors';

export interface USBDevice {
  name: string;
  size: number;
  vendor: string;
}

class USBDeviceManager {
  private device: USBDevice | null = null;

  async isSupported(): Promise<boolean> {
    return 'usb' in navigator;
  }

  async requestDevice(): Promise<void> {
    if (!('usb' in navigator)) {
      throw createError('WEBUSB_NOT_SUPPORTED');
    }

    try {
      logger.info('Requesting USB device access');

      const filters = [
        { classCode: 0x08 },
      ];

      const device = await (navigator as any).usb.requestDevice({ filters });

      logger.debug('USB device selected', {
        vendorId: device.vendorId,
        productId: device.productId,
      });

      this.device = {
        name: device.productName || `USB Device ${device.productId}`,
        size: 0,
        vendor: device.manufacturerName || 'Unknown',
      };
    } catch (error) {
      if ((error as Error).name === 'NotFoundError') {
        throw createError('NO_DEVICE_FOUND');
      }
      throw error;
    }
  }

  async getDeviceInfo(size: number): Promise<USBDevice> {
    if (!this.device) {
      throw createError('NO_DEVICE_FOUND');
    }

    return {
      ...this.device,
      size,
    };
  }

  getSelectedDevice(): USBDevice | null {
    return this.device;
  }

  clearDevice(): void {
    this.device = null;
  }
}

export const usbManager = new USBDeviceManager();

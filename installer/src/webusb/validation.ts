import { logger } from '../utils/logger';

interface ValidationResult {
  isValid: boolean;
  message: string;
  warning?: string;
}

class Validator {
  validateImageSize(imageSizeGB: number, deviceSizeGB: number): ValidationResult {
    if (deviceSizeGB < imageSizeGB) {
      return {
        isValid: false,
        message: `Image is ${imageSizeGB} GB, but device is only ${deviceSizeGB} GB`,
      };
    }

    const remainingGB = deviceSizeGB - imageSizeGB;
    if (remainingGB < 1) {
      return {
        isValid: true,
        message: `Image is ${imageSizeGB} GB, device is ${deviceSizeGB} GB`,
        warning: `Only ${remainingGB.toFixed(1)} GB remaining. Works, but minimal headroom.`,
      };
    }

    return {
      isValid: true,
      message: `Image is ${imageSizeGB} GB, device is ${deviceSizeGB} GB (${remainingGB.toFixed(1)} GB remaining)`,
    };
  }

  validateDeviceSize(minSizeGB: number, deviceSizeGB: number): ValidationResult {
    logger.debug('Validating device size', { minSizeGB, deviceSizeGB });

    if (deviceSizeGB < minSizeGB) {
      return {
        isValid: false,
        message: `This Pi model requires at least ${minSizeGB} GB, but device is ${deviceSizeGB} GB`,
      };
    }

    return {
      isValid: true,
      message: `Device size is sufficient (${deviceSizeGB} GB)`,
    };
  }

  async validateDevice(): Promise<ValidationResult> {
    logger.info('Validating device');

    if (!('usb' in navigator)) {
      return {
        isValid: false,
        message: 'WebUSB not supported',
      };
    }

    try {
      const devices = await (navigator as any).usb.getDevices();
      if (devices.length === 0) {
        return {
          isValid: false,
          message: 'No USB device found',
        };
      }

      logger.debug('Device validation passed');
      return {
        isValid: true,
        message: 'Device is valid',
      };
    } catch (error) {
      logger.error('Device validation failed', error);
      return {
        isValid: false,
        message: 'Failed to access USB device',
      };
    }
  }
}

export const validator = new Validator();

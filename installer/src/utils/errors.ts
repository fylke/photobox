export class ImagerError extends Error {
  constructor(
    public code: string,
    message: string,
    public suggestion?: string
  ) {
    super(message);
    this.name = 'ImagerError';
  }
}

const errorMap: Record<string, { message: string; suggestion: string }> = {
  WEBUSB_NOT_SUPPORTED: {
    message: 'Your browser does not support WebUSB',
    suggestion: 'Please use Chrome, Edge, or Brave browser',
  },
  NO_DEVICE_FOUND: {
    message: 'No SD card reader detected',
    suggestion: 'Check that your SD card reader is connected via USB',
  },
  DEVICE_TOO_SMALL: {
    message: 'SD card is too small for this image',
    suggestion: 'Use a larger SD card',
  },
  DOWNLOAD_FAILED: {
    message: 'Failed to download image',
    suggestion: 'Check your internet connection and try again',
  },
  WRITE_FAILED: {
    message: 'Failed to write image to SD card',
    suggestion: 'Try a different USB cable or SD card reader',
  },
  OUT_OF_MEMORY: {
    message: 'Not enough memory available',
    suggestion: 'Close other tabs and try again',
  },
  DEVICE_MOUNTED: {
    message: 'SD card is in use by your system',
    suggestion: 'Eject the SD card and try again',
  },
};

export function createError(code: string, customMessage?: string): ImagerError {
  const config = errorMap[code];
  const message = customMessage || config?.message || code;
  const suggestion = config?.suggestion;
  return new ImagerError(code, message, suggestion);
}

export function getUserFriendlyError(error: unknown): string {
  if (error instanceof ImagerError) {
    if (error.suggestion) {
      return `${error.message}\n\n💡 ${error.suggestion}`;
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

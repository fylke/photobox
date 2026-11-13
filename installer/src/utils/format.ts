export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 10) / 10 + ' ' + sizes[i];
}

export function formatSpeed(bytesPerSecond: number): string {
  return formatBytes(bytesPerSecond) + '/s';
}

export function formatETA(seconds: number): string {
  if (seconds < 60) {
    return Math.round(seconds) + 's';
  }
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return minutes + 'm ' + secs + 's';
}

export function calculateETA(bytesRemaining: number, bytesPerSecond: number): number {
  if (bytesPerSecond <= 0) return 0;
  return bytesRemaining / bytesPerSecond;
}

export async function downloadFile(
  url: string,
  onProgress?: (downloaded: number, total: number) => void
): Promise<ArrayBuffer> {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status} ${response.statusText}`);
  }

  const total = parseInt(response.headers.get('content-length') || '0', 10);
  let downloaded = 0;

  if (!response.body) {
    throw new Error('Response body is empty');
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      chunks.push(value);
      downloaded += value.length;

      if (onProgress) {
        onProgress(downloaded, total);
      }
    }
  } finally {
    reader.releaseLock();
  }

  const result = new Uint8Array(downloaded);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }

  return result.buffer;
}

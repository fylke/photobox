import assert from 'node:assert/strict';
import { constants, openAsBlob } from 'node:fs';
import { copyFile, mkdtemp, open, rename, rmdir, unlink, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test, { after } from 'node:test';
import { build } from 'esbuild';

const testDirectory = await mkdtemp(join(tmpdir(), 'photobox-image-test-'));
const bundle = join(testDirectory, 'prepare.cjs');
const root = process.env.PHOTOBOX_TEST_TEMP || testDirectory;
await build({
  entryPoints: [fileURLToPath(new URL('../src/imaging/prepareImage.ts', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  define: {
    'import.meta.env.BASE_URL': JSON.stringify(
      process.env.PHOTOBOX_TEST_BASE_URL || 'http://127.0.0.1:37841/photobox/installer/',
    ),
  },
  outfile: bundle,
});
after(async () => {
  await unlink(bundle);
  await rmdir(testDirectory);
});

class LocalFileHandle {
  constructor(path, seeks = []) {
    this.path = path;
    this.seeks = seeks;
  }

  async getFile() {
    return openAsBlob(this.path);
  }

  async createWritable(options = {}) {
    const temporary = `${this.path}.swap`;
    if (options.keepExistingData) {
      await copyFile(this.path, temporary, constants.COPYFILE_FICLONE);
    } else {
      await writeFile(temporary, '');
    }
    const file = await open(temporary, 'r+');
    let position = 0;
    const write = async (data) => {
      let written = 0;
      while (written < data.length) {
        const result = await file.write(data, written, data.length - written, position);
        position += result.bytesWritten;
        written += result.bytesWritten;
      }
    };
    const close = async () => {
      await file.close();
      await rename(temporary, this.path);
    };
    const abort = async () => {
      await file.close();
      await unlink(temporary);
    };
    const stream = new WritableStream({ write, close, abort });
    stream.write = write;
    stream.seek = async (offset) => { position = offset; this.seeks.push(offset); };
    stream.close = close;
    return stream;
  }
}

test('streams, verifies and configures a real image', { skip: !process.env.PHOTOBOX_TEST_TEMP }, async () => {
  const { getImageManifest, prepareImage } = await import(pathToFileURL(bundle));
  const seeks = [];
  const directory = {
    getFileHandle: async (name) => {
      const path = join(root, name);
      await writeFile(path, '');
      return new LocalFileHandle(path, seeks);
    },
    removeEntry: async (name) => unlink(join(root, name)),
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { storage: { getDirectory: async () => directory } },
  });

  const result = join(root, 'prepared-test-image.img');
  try {
    const progress = [];
    await prepareImage(new LocalFileHandle(result), await getImageManifest(), 'GB', true, (text) => {
      progress.push(text);
    });
    assert.ok(progress.includes('Applying Wi-Fi and boot settings...'));
    assert.ok(progress.includes('Saving the configured image...'));
    const file = await open(result, 'r');
    try {
      assert.ok(seeks.length >= 2);
      const content = Buffer.alloc(65536);
      await file.read(content, 0, content.length, seeks[0]);
      assert.notEqual(content.indexOf('cfg80211.ieee80211_regdom=GB'), -1);
      assert.notEqual(content.indexOf('photobox.debug=1'), -1);
    } finally {
      await file.close();
    }
  } finally {
    try {
      await unlink(result);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
});

test('rejects a downloaded image with a bad checksum', async () => {
  const { prepareImage } = await import(pathToFileURL(bundle));
  const compressed = spawnSync('xz', ['-c'], { input: Buffer.from('not an image') });
  assert.equal(compressed.status, 0);
  const originalFetch = globalThis.fetch;
  const directory = {
    getFileHandle: async (name) => {
      const path = join(root, name);
      await writeFile(path, '');
      return new LocalFileHandle(path);
    },
    removeEntry: async (name) => unlink(join(root, name)),
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { storage: { getDirectory: async () => directory } },
  });
  globalThis.fetch = async () => new Response(compressed.stdout);
  try {
    const destination = new LocalFileHandle(join(root, 'bad-checksum-result.img'));
    await assert.rejects(
      prepareImage(
        destination,
        { sha256: '0'.repeat(64), size: compressed.stdout.length, bootDebug: true },
        'GB',
        true,
        () => {},
      ),
      /checksum mismatch/,
    );
    await assert.rejects(open(destination.path, 'r'), { code: 'ENOENT' });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

import assert from 'node:assert/strict';
import { openAsBlob } from 'node:fs';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/imaging/bootConfig.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { configureCommandLine, customizeBoot } = await import(
  `data:text/javascript;base64,${Buffer.from(js).toString('base64')}`
);

function fakeImage(commandLine) {
  const image = new Uint8Array(102 * 512);
  const view = new DataView(image.buffer);
  view.setUint16(510, 0xaa55, true);
  image[450] = 0x0c;
  view.setUint32(454, 2, true);
  view.setUint32(458, 100, true);
  const boot = 2 * 512;
  view.setUint16(boot + 11, 512, true);
  image[boot + 13] = 1;
  view.setUint16(boot + 14, 1, true);
  image[boot + 16] = 1;
  view.setUint32(boot + 32, 100, true);
  view.setUint32(boot + 36, 1, true);
  view.setUint32(boot + 44, 2, true);
  view.setUint32(3 * 512 + 2 * 4, 0x0fffffff, true);
  view.setUint32(3 * 512 + 3 * 4, 0x0fffffff, true);
  const entry = 4 * 512;
  image.set(new TextEncoder().encode('CMDLINE TXT'), entry);
  image[entry + 11] = 0x20;
  view.setUint16(entry + 26, 3, true);
  const content = new TextEncoder().encode(commandLine);
  view.setUint32(entry + 28, content.length, true);
  image.set(content, 5 * 512);
  return image;
}

function memoryHandle(initial) {
  let contents = initial;
  return {
    getFile: async () => new Blob([contents]),
    createWritable: async () => {
      const updated = contents.slice();
      let position = 0;
      return {
        seek: async (offset) => { position = offset; },
        write: async (data) => { updated.set(data, position); position += data.length; },
        close: async () => { contents = updated; },
        abort: async () => {},
      };
    },
    bytes: () => contents,
  };
}

test('configures a FAT boot file with country and persistent debug', async () => {
  const handle = memoryHandle(fakeImage('console=tty1 rootwait quiet cfg80211.ieee80211_regdom=US\n'));
  await customizeBoot(handle, 'GB', true);
  const bytes = handle.bytes();
  const size = new DataView(bytes.buffer).getUint32(4 * 512 + 28, true);
  const command = new TextDecoder().decode(bytes.slice(5 * 512, 5 * 512 + size));
  assert.match(command, /cfg80211\.ieee80211_regdom=GB/);
  assert.doesNotMatch(command, /\bquiet\b|regdom=US/);
  assert.match(command, /\bphotobox\.debug=1\b/);
  assert.match(command, /\bsystemd\.log_target=kmsg\b/);
  assert.equal((command.match(/console=tty1/g) ?? []).length, 1);
});

test('debug is opt-in and invalid input is rejected', () => {
  const line = configureCommandLine('rootwait quiet', 'NO', false);
  assert.match(line, /\bquiet\b/);
  assert.doesNotMatch(line, /photobox\.debug/);
  assert.throws(() => configureCommandLine('rootwait', 'NOR', true), /country/);
  assert.throws(() => configureCommandLine('rootwait\nextra', 'NO', true), /command line/);
});

test('rejects invalid images without writing', async () => {
  const image = fakeImage('rootwait');
  image[450] = 0x83;
  const handle = memoryHandle(image);
  await assert.rejects(customizeBoot(handle, 'GB', true), /FAT32/);
  assert.deepEqual(handle.bytes(), image);
});

test('configures the published image boot partition', { skip: !process.env.PHOTOBOX_TEST_IMAGE }, async () => {
  const image = await openAsBlob(process.env.PHOTOBOX_TEST_IMAGE);
  const writes = [];
  let position = 0;
  const handle = {
    getFile: async () => image,
    createWritable: async () => ({
      seek: async (offset) => { position = offset; },
      write: async (data) => { writes.push({ position, data: Uint8Array.from(data) }); },
      close: async () => {},
      abort: async () => {},
    }),
  };
  await customizeBoot(handle, 'GB', true);
  const command = new TextDecoder().decode(writes[0].data);
  assert.match(command, /cfg80211\.ieee80211_regdom=GB/);
  assert.match(command, /photobox\.debug=1/);
  assert.ok(writes.at(-1).data.length === 4);
});

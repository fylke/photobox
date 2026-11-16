interface BootFile {
  offsets: number[];
  entryOffset: number;
  clusterSize: number;
  size: number;
}

async function readAt(image: Blob, offset: number, length: number): Promise<Uint8Array> {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset + length > image.size) {
    throw new Error('Image contains an invalid filesystem offset');
  }
  const result = new Uint8Array(await image.slice(offset, offset + length).arrayBuffer());
  if (result.length !== length) throw new Error('Image is truncated');
  return result;
}

function dataView(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

async function findBootFile(image: Blob): Promise<BootFile> {
  const mbr = await readAt(image, 0, 512);
  const mbrView = dataView(mbr);
  if (mbrView.getUint16(510, true) !== 0xaa55 || ![0x0b, 0x0c].includes(mbr[450])) {
    throw new Error('Image does not have a supported FAT32 boot partition');
  }
  const partitionOffset = mbrView.getUint32(454, true) * 512;
  const partitionSize = mbrView.getUint32(458, true) * 512;
  if (!partitionSize || partitionOffset + partitionSize > image.size) {
    throw new Error('Image has an invalid boot partition');
  }
  const boot = dataView(await readAt(image, partitionOffset, 512));
  const sectorSize = boot.getUint16(11, true);
  const sectorsPerCluster = boot.getUint8(13);
  const reserved = boot.getUint16(14, true);
  const fatCount = boot.getUint8(16);
  const fatSectors = boot.getUint32(36, true);
  const rootCluster = boot.getUint32(44, true);
  const totalSectors = boot.getUint16(19, true) || boot.getUint32(32, true);
  if (
    ![512, 1024, 2048, 4096].includes(sectorSize) ||
    !sectorsPerCluster ||
    (sectorsPerCluster & (sectorsPerCluster - 1)) !== 0 ||
    !reserved || !fatCount || !fatSectors ||
    boot.getUint16(17, true) !== 0 ||
    totalSectors * sectorSize > partitionSize
  ) {
    throw new Error('Unsupported or invalid FAT32 filesystem');
  }
  const clusterSize = sectorSize * sectorsPerCluster;
  const dataSectors = totalSectors - reserved - fatCount * fatSectors;
  const maxCluster = Math.floor(dataSectors / sectorsPerCluster) + 1;
  const fatOffset = partitionOffset + reserved * sectorSize;
  const dataOffset = partitionOffset + (reserved + fatCount * fatSectors) * sectorSize;
  if (dataSectors <= 0 || maxCluster * 4 + 4 > fatSectors * sectorSize) {
    throw new Error('Invalid FAT32 allocation table');
  }

  const clusterOffset = (cluster: number): number => {
    if (cluster < 2 || cluster > maxCluster) throw new Error('Invalid FAT32 cluster');
    return dataOffset + (cluster - 2) * clusterSize;
  };
  const nextCluster = async (cluster: number): Promise<number> => {
    const bytes = await readAt(image, fatOffset + cluster * 4, 4);
    return dataView(bytes).getUint32(0, true) & 0x0fffffff;
  };
  const clusters = async (first: number): Promise<number[]> => {
    const result: number[] = [];
    const seen = new Set<number>();
    let current = first;
    while (current < 0x0ffffff8) {
      clusterOffset(current);
      if (seen.has(current) || result.length >= 65536) throw new Error('Invalid FAT32 chain');
      seen.add(current);
      result.push(current);
      current = await nextCluster(current);
    }
    return result;
  };

  let bootFile: BootFile | null = null;
  let end = false;
  for (const cluster of await clusters(rootCluster)) {
    const offset = clusterOffset(cluster);
    const directory = await readAt(image, offset, clusterSize);
    for (let position = 0; position < directory.length; position += 32) {
      if (directory[position] === 0) {
        end = true;
        break;
      }
      if (directory[position] === 0xe5 || (directory[position + 11] & 0x18) !== 0) continue;
      const name = new TextDecoder().decode(directory.slice(position, position + 11));
      if (name !== 'CMDLINE TXT') continue;
      if (bootFile) throw new Error('Image contains multiple cmdline.txt files');
      const entry = dataView(directory.subarray(position, position + 32));
      const firstCluster = (entry.getUint16(20, true) << 16) | entry.getUint16(26, true);
      const fileClusters = await clusters(firstCluster >>> 0);
      const size = entry.getUint32(28, true);
      if (!size || size > fileClusters.length * clusterSize || fileClusters.length * clusterSize > 65536) {
        throw new Error('Invalid cmdline.txt allocation');
      }
      bootFile = {
        offsets: fileClusters.map(clusterOffset),
        entryOffset: offset + position,
        clusterSize,
        size,
      };
    }
    if (end) break;
  }
  if (!bootFile) throw new Error('Image boot partition has no cmdline.txt');
  return bootFile;
}

export function configureCommandLine(original: string, country: string, debug: boolean): string {
  if (!/^[A-Z]{2}$/.test(country)) throw new Error('Invalid Wi-Fi country');
  const line = original.trim();
  if (!line || /[\r\n\0]/.test(line) || /[^\x20-\x7e]/.test(line)) {
    throw new Error('Invalid boot command line');
  }
  const tokens = line.split(/\s+/).filter((token) => {
    if (token.startsWith('cfg80211.ieee80211_regdom=') || token.startsWith('photobox.debug=')) {
      return false;
    }
    if (!debug) return true;
    return !(
      ['quiet', 'splash', 'ignore_loglevel'].includes(token) ||
      /^(loglevel|systemd\.log_level|systemd\.log_target|systemd\.show_status)=/.test(token)
    );
  });
  tokens.push(`cfg80211.ieee80211_regdom=${country}`);
  if (debug) {
    if (!tokens.includes('console=tty1')) tokens.push('console=tty1');
    tokens.push(
      'photobox.debug=1',
      'ignore_loglevel',
      'loglevel=7',
      'systemd.log_level=debug',
      'systemd.log_target=kmsg',
      'systemd.show_status=1',
    );
  }
  return `${tokens.join(' ')}\n`;
}

export async function customizeBoot(
  handle: FileSystemFileHandle,
  country: string,
  debug: boolean,
): Promise<void> {
  const image = await handle.getFile();
  const file = await findBootFile(image);
  const bytes = new Uint8Array(file.offsets.length * file.clusterSize);
  for (let index = 0; index < file.offsets.length; index++) {
    bytes.set(await readAt(image, file.offsets[index], file.clusterSize), index * file.clusterSize);
  }
  const original = new TextDecoder().decode(bytes.slice(0, file.size));
  const updated = new TextEncoder().encode(configureCommandLine(original, country, debug));
  if (updated.length > bytes.length) {
    throw new Error('The image does not have enough boot configuration space');
  }
  bytes.fill(0);
  bytes.set(updated);
  const writable = await handle.createWritable({ keepExistingData: true });
  try {
    for (let index = 0; index < file.offsets.length; index++) {
      await writable.seek(file.offsets[index]);
      await writable.write(bytes.slice(index * file.clusterSize, (index + 1) * file.clusterSize));
    }
    const size = new Uint8Array(4);
    dataView(size).setUint32(0, updated.length, true);
    await writable.seek(file.entryOffset + 28);
    await writable.write(size);
    await writable.close();
  } catch (error) {
    await writable.abort();
    throw error;
  }
}

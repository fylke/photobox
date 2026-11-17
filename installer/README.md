# Photobox image preparation

The [web installer](https://fylke.github.io/photobox/installer/) prepares a configured Raspberry Pi image locally in the browser. Use Raspberry Pi Imager's **Use custom** option to write the resulting `.img` file to an SD card.

Select the Wi-Fi country and optionally enable persistent boot debug before preparing the image. Debug output appears on the boot console where available; journal output is saved to the card's boot partition, capped at 200 MiB. The logs can contain sensitive information. See [First Boot and Pairing](../docs/first-boot-and-pairing.md) for retrieval, limitations, and disabling debug.

The installer requires a current Chrome or Edge browser with the File System Access and origin-private file system APIs. Use a regular browser window: private browsing can impose much smaller storage limits. Image preparation needs several gigabytes of free local disk space. The base image is downloaded, checked against its release SHA256, decompressed and configured locally. The saved image is uncompressed; do not close the page until preparation finishes. Neither the prepared image nor the selected settings are uploaded.

## Development

Node.js 20 and npm are required.

```sh
cd installer
npm ci
npm test
npm run build
```

`npm run dev` starts the Vite development server. To exercise image preparation locally, stage an image and its `SHA256SUMS` with `python3 tools/stage_installer_image.py RELEASE_DIR installer/public/image` from the repository root. Add `photobox-image-capabilities.json` with `{"boot_debug": true}` only for an image containing the boot-debug service.

The HTML entrypoint, `index.html`, is tracked in Git and used directly by local and CI builds.

The Pages workflows stage one verified prerelease base image and its manifest under `installer/image`. Older releases without capability metadata do not offer boot debug. A newly built release is required before boot debug becomes available on the live page. GitHub Pages limits published sites to 1 GB and has a soft bandwidth limit of 100 GB per month.

Image preparation and first-boot behavior still require physical Raspberry Pi validation.

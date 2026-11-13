# Photobox Web Installer

A zero-installation web-based installer for Photobox. No download, no installation—just open a link and write your SD card.

**Live:** https://fylke.github.io/photobox/installer

## Features

- ✅ **Zero Installation**: Open in any Chrome/Edge/Brave browser
- ✅ **Fast Setup**: Write images in 5-10 minutes
- ✅ **Debug Mode**: Real-time logging for troubleshooting
- ✅ **Three Pi Models**: Support for Pi 3, Pi 4, and Pi 5
- ✅ **WiFi Configuration**: Select your country for correct WiFi regulatory domain
- ✅ **Image Size Display**: Clear information about SD card requirements
- ✅ **Progress Tracking**: Live download and write speed, ETA

## Usage

1. Open https://fylke.github.io/photobox/installer in your browser (Chrome, Edge, or Brave)
2. Select your Raspberry Pi model (3, 4, or 5)
3. Select your WiFi country
4. Connect your SD card reader
5. Review and confirm
6. Watch as the image downloads and writes to your SD card

## Development

### Prerequisites

- Node.js 16+
- npm

### Setup

```bash
cd installer
npm install
```

### Development Server

```bash
npm run dev
```

Open http://localhost:5173 in your browser.

### Build

```bash
npm run build
```

Output goes to `dist/`.

### Debug Mode

Enable debug mode by:
1. Adding `?debug=true` to the URL
2. Checking "Enable debug logging" on the review screen
3. Pressing `Ctrl+Shift+D`

The debug panel shows real-time logs with timestamps and helps troubleshoot issues.

## Architecture

### `/src/config.ts`
- Pi model and country configurations
- Image size and SD card requirements

### `/src/ui/`
- React components for each screen (splash, hardware selection, country picker, progress, etc.)
- Debug panel component

### `/src/webusb/`
- WebUSB device access
- Image writer
- Validation

### `/src/imaging/`
- Image downloader with caching
- Image processor (WiFi domain injection)

### `/src/utils/`
- Logger with debug mode
- Error handling
- Format utilities (bytes, speed, ETA)

## Troubleshooting

### "Your browser does not support WebUSB"
Use Chrome, Edge, or Brave (latest versions). Firefox and Safari don't support WebUSB.

### "No SD card reader detected"
- Check the USB connection
- Try a different USB cable
- Try a different USB port
- Enable debug mode to see detailed device information

### "SD card is too small"
Use a larger SD card. Requirements:
- Pi 3: at least 4 GB
- Pi 4: at least 8 GB
- Pi 5: at least 16 GB

### Enable debug logging
Add `?debug=true` to the URL or check the debug checkbox on the review screen to see detailed logs.

## Deployment

The installer is automatically deployed to GitHub Pages when changes are pushed to the `main` branch. It's hosted at https://fylke.github.io/photobox/installer.

### Manual Deployment

```bash
npm run build
cp -r dist/* ../../docs/installer/
git add -A
git commit -m "Update installer"
git push
```

## Code Size

- **Core logic**: ~1,750–2,000 lines
- **UI components**: ~600–800 lines
- **Bundle size**: ~165 KB (uncompressed), ~53 KB (gzipped)

## Browser Support

| Browser | Support |
|---------|---------|
| Chrome 61+ | ✅ |
| Edge 79+ | ✅ |
| Brave | ✅ |
| Firefox | ❌ |
| Safari | ❌ |

## License

Same as Photobox (see main repository).

## Contributing

Improvements, bug reports, and suggestions are welcome! Open an issue or PR in the main Photobox repository.

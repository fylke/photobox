# First Boot and Pairing

> **Status:** Pi setup and networking have not yet been validated on physical hardware. Use a disposable card and isolated test network. Maintainers: see [Hardware Validation](hardware-validation-m2.md).

For setup on an existing computer instead of a Pi, see [Run on this computer](../README.md#run-on-this-computer).

You need a Raspberry Pi, a microSD card and reader, a Windows/macOS/Linux computer, and the Wi-Fi country code where the Pi will operate.

## Prepare one Pi

### 1. Get the generic image

Download the `.img.xz` image, `SHA256SUMS`, and the setup executable for your computer from the same prerelease. Alternatively, download and extract the `photobox-raspios-arm64` artifact from a successful **Build Raspberry Pi image** run in GitHub Actions; artifacts are retained for 30 days. Keep the files together in one folder. Older images do not support this setup method.

Choose `photobox-setup-windows-x64.exe` for Windows, `photobox-setup-linux-x64` for Linux, or `photobox-setup-macos-arm64` / `photobox-setup-macos-x64` for an Apple Silicon / Intel Mac. No Python installation is needed. Windows ARM and Linux ARM builds are not currently available.

### 2. Create credentials

Choose a new, empty output directory for this Pi. Replace `US` with the two-letter ISO country code where the Pi will operate. On Windows PowerShell, from the folder containing the downloads:

```powershell
.\photobox-setup-windows-x64.exe --wifi-country US --output-dir "$HOME\photobox-device-setup"
```

On Linux, from the downloads folder:

```sh
chmod +x ./photobox-setup-linux-x64
./photobox-setup-linux-x64 --wifi-country US --output-dir "$HOME/photobox-device-setup"
```

On macOS, use the same commands with `photobox-setup-macos-arm64` or `photobox-setup-macos-x64` in place of `photobox-setup-linux-x64`. The executables are not currently signed or notarized, so your operating system may warn or block them.

The tool checks the downloads and creates `photobox-device.json` and `wifi-join.svg`. It prints the Wi-Fi name, password, and a one-time setup PIN. Record the PIN privately; it will not be shown again. Open `wifi-join.svg` in a browser to display or print the Wi-Fi QR.

Keep the output and printed credentials private. On Windows, use a private user folder and restrict access using Windows permissions. If verification fails, download matching files from the same build and retry with a new output directory.

### 3. Flash the image and copy the setup file

Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or use another image writer that supports a custom image. In Imager, choose **Use custom** and select the downloaded generic `.img.xz`, then select the intended microSD card. **Writing the image erases the selected card. Confirm the card's device and capacity before starting.** Do not add a separate Wi-Fi configuration in the imaging tool.

When writing finishes, remove and reinsert the card if the computer does not show its boot partition. Open the partition named `bootfs` and copy the generated `photobox-device.json` into its top-level folder. On Windows, do not format any other partition if prompted. Eject the card safely, put it in the Pi, connect the camera, and power on.

The Pi imports the file on first boot and removes the boot-partition copy. The file contains the Wi-Fi password; keep the card private. Deletion does not guarantee secure erasure.

## Claim the booth as administrator

1. Connect your phone or laptop to the printed Wi-Fi network or scan `wifi-join.svg`. If it says “No internet,” choose to stay connected.
2. Open `http://photobox.local:8000`. If that fails on the Pi hotspot, try `http://10.42.0.1:8000`.
3. Enter the setup PIN. This browser becomes the administrator; the PIN is consumed and can be discarded. Never share it with guests.
4. Check camera and storage status. Setup remains accessible without a camera, but sessions cannot start until one is available.

## Connect to the venue network

Optionally, enter the venue Wi-Fi name and password on the administrator page. WPA-Personal is supported; enterprise Wi-Fi and captive portals are not. The setup hotspot turns off after the Pi connects successfully and remains available if connection fails. Saved venue Wi-Fi is retried after reboot. Local capture does not require internet access.

## Invite guests

Create an invitation on the administrator page. Guests first join a network that can reach the Pi, then scan the invitation QR or open its link. The **Wi-Fi QR** connects them to a network; the **guest invitation** grants Photobox access. Invitations expire and guest access can be revoked.

## If the setup PIN is lost

If the PIN is lost before the first administrator claim, it cannot be retrieved: the Pi stores only its hash. For a fresh installation with no data to keep, flash the generic image again and generate a new credential bundle and PIN using the steps above. Reflashing erases the card, so first back up anything already on it that you need to keep.

After the first administrator claim, the PIN is consumed and no longer needed. If you lose access to the administrator browser later, the old PIN cannot restore access. There is currently no documented, tested administrator recovery procedure, and the image disables SSH. Preserve the card and any photos, and ask the project maintainer for a recovery procedure before making changes. A guest invitation cannot restore administrator access.

## If setup does not work

- **Pi network missing:** check power, the image, and that `photobox-device.json` was copied to the boot partition.
- **Page does not open:** confirm the phone is on a network that can reach the Pi. On its hotspot, try `http://10.42.0.1:8000`; on venue Wi-Fi, use the address shown on the admin page or router.
- **PIN rejected:** check the digits and whether it was already used. Attempts are rate-limited; see [If the setup PIN is lost](#if-the-setup-pin-is-lost).
- **Guest cannot pair:** check network reachability and whether the invitation expired or was revoked.

# First Boot and Pairing

> **Status:** Phone pairing, the local one-time PIN command, first-boot provisioning, setup hotspot configuration, and admin-controlled venue Wi-Fi setup are implemented. The image and network paths have not yet been validated on physical Pi hardware.

Maintainers: the physical acceptance procedure is in [Milestone 2 Hardware Validation](hardware-validation-m2.md). Do not mark the setup flow complete until that checklist passes on the supported Pi/OS.

This guide is for someone setting up a Photobox without needing to know Linux networking or security terminology. It explains what the computer creates, what to put on the Pi, and what the different codes are for.

## Choose a setup path

**Already have Photobox running on a computer?** Use the [local-host steps](#available-now-local-pairing-on-an-installed-host). The computer and phone must already be on a network that can reach each other. This path does not create a hotspot.

**Setting up a Raspberry Pi?** Continue with [Prepare one Pi](#prepare-one-pi). You need a Windows, macOS, or Linux computer, a microSD card and reader, the Wi-Fi country code for the Pi's location, and the credentials for an optional venue Wi-Fi network. The first-boot and network features have not yet passed physical hardware validation; use a test Pi, disposable card, and isolated network.

At a glance: obtain and verify the image and tool, flash the generic image, generate credentials, copy the setup file to the card, boot the Pi, and claim admin access. Guest invitation is a separate step after admin setup.

These are two different operations: **joining Wi-Fi connects a device to the Pi’s network; accepting an invitation gives that device guest access to Photobox.**

## Available now: local pairing on an installed host

This is the development flow for an already-installed host. Network management requires a provisioned Pi image:

1. Install Photobox on a host and choose a data directory. Keep the same `PHOTOBOX_DATA_DIR` for the setup command and daemon if you override its default.
2. Run `photobox-setup-pin` in a trusted terminal. It prints a random 6-digit PIN once and stores only a slow hash in `pairing.sqlite3`. Record the PIN privately; the command refuses to replace it after setup is initialized.
3. Start `photobox` and open its address from a phone or laptop already on a network that can reach the host.
4. Enter the PIN to claim admin access. From the admin page, create a guest invitation QR or copy its short-lived link. Guests must already be on a reachable network before they scan/open the invitation.
5. Guests can view the active session; one phone controls it. The admin can revoke guest access from the paired-phone list.

The local command does not create an SD-card image, configure a Wi-Fi password, or start an access point.

The Pi's first-boot importer installs its setup hotspot profile and regulatory country. An admin can configure a WPA-Personal venue network from the admin page; NetworkManager verifies a DHCP address and gateway before the setup hotspot is disabled. Enterprise Wi-Fi and captive-portal login are not supported.

## Three codes, three purposes

`photobox-setup-pin` initializes an already-installed host. The standalone provisioner generates per-device credentials for a flashed generic image; no image modification tools are needed.

- **Wi-Fi join code:** contains the visible network name and Wi-Fi password. It lets a phone or laptop connect to the Pi’s network. It does not sign the person in to Photobox.
- **Setup PIN:** a unique, one-time 6-digit number for the first administrator claim. It is not the Wi-Fi password and is not shared with guests. The local provisioning tool shows it when preparing that Pi’s image. The Pi stores only a hash and invalidates the PIN after a successful claim.
- **Guest invitation QR:** a short-lived invitation created by the administrator. It pairs one guest browser with the booth. It is not an administrator credential and does not contain the Wi-Fi password.

Do not combine these codes or post them in a public place. A hidden Wi-Fi name would not make the network secure; use the unique Wi-Fi password and separate Photobox credentials instead.

## Prepare one Pi

### 1. Get the generic image

The image is a minimal 64-bit Raspberry Pi OS image with Photobox installed. It is generic: it does not yet contain the Wi-Fi credentials or setup PIN for your device.

- For an alpha, beta, or release-candidate build, download the `.img.xz` image, the `photobox-setup-*` executable for your computer, and `SHA256SUMS` from that GitHub prerelease.
- For a workflow build, open the repository's **Actions** tab, select a successful **Build Raspberry Pi image** run, and download its `photobox-raspios-arm64` artifact. GitHub downloads this artifact as a ZIP; extract it before continuing. It contains the image, the setup executables, and their checksums. The artifact is retained for 30 days.

Keep the image, executable, and checksum file together in the same folder and use files from the same build. Older images do not contain the first-boot importer.

### 2. Get the provisioning tool

Choose `photobox-setup-windows-x64.exe` for Windows on an x64 computer, `photobox-setup-linux-x64` for Linux on x64, or `photobox-setup-macos-arm64` or `photobox-setup-macos-x64` for an Apple Silicon or Intel Mac respectively. The executable includes its runtime; you do not need to install Python or other dependencies. These builds do not currently cover Windows ARM or Linux ARM. Keep the computer and terminal private while the PIN and Wi-Fi password are displayed.

### 3. Create per-device credentials

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

The command creates `photobox-device.json` and `wifi-join.svg` in that directory. If the downloaded files are missing or do not match, it stops without creating credentials; download the matching files again before retrying. It prints the device's Wi-Fi name, Wi-Fi password, and one-time 6-digit setup PIN. Save the PIN privately; it cannot be displayed again. The file contains the PIN hash, not the PIN itself. The output directory must be new or empty. On Linux and macOS, the tool restricts the files to the owner; on Windows, use a private user folder and restrict access using Windows permissions.

Open `wifi-join.svg` in a browser to display or print the Wi-Fi join QR.

Keep the credential bundle private. Do not commit it, attach it to a public issue, put it in shared CI artifacts, or paste the printed secrets into a chat. The Wi-Fi QR is for joining the Pi's network; the setup PIN is for the first admin claim.

### 4. Flash the image and copy the setup file

Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or use another image writer that supports a custom image. In Imager, choose **Use custom** and select the downloaded generic `.img.xz`, then select the intended microSD card. **Writing the image erases the selected card. Confirm the card's device and capacity before starting.** Do not add a separate Wi-Fi configuration in the imaging tool.

When writing finishes, remove and reinsert the card if the computer does not show its boot partition. Open the partition named `bootfs` and copy the generated `photobox-device.json` into its top-level folder. On Windows, do not format any other partition if prompted. Eject the card safely, put it in the Pi, connect the camera, and power on.

On first boot the Pi installs the PIN hash and Wi-Fi settings, then removes the boot-partition copy. The copy contains the Wi-Fi password and is readable by anyone with the card; keep it private before and after setup. Deletion does not guarantee secure erasure from an SD card. The Pi advertises the printed Wi-Fi name and `photobox.local`; while directly connected to its hotspot, `10.42.0.1` is the fallback address.

## Claim the booth as administrator

1. On a phone or laptop, scan the Wi-Fi join code or select the printed network name and enter its password. The setup network may say “No internet”; that is expected while connected directly to the Pi. Choose to remain connected.
2. Open `http://photobox.local:8000`. If the phone cannot resolve that name while connected to the setup hotspot, use `http://10.42.0.1:8000`.
3. Enter the one-time setup PIN from the provisioning step. The first successful claim makes this browser the booth administrator. The PIN is then invalid and cannot be reused.
4. Confirm the camera and storage status. If the camera is unavailable, the service should still be reachable for setup, but photo sessions cannot start until a supported camera is available. The admin page is separate from the guest controller.

The Pi stores only a hash of the setup PIN. Failed claims are rate-limited. Never send the PIN as part of a URL or guest QR code.

## Connect to the venue network

From the administrator page, enter the venue Wi-Fi name and password. The first implementation supports WPA-Personal networks (not enterprise sign-in or captive portals). The Pi keeps the setup hotspot available while it checks that the venue connection has an address and gateway. After a successful connection, it turns off the setup hotspot. Guests can use the venue Wi-Fi to reach Photobox.

If venue Wi-Fi is unavailable or the Pi cannot connect, the setup hotspot remains available. A saved venue network is retried after reboot; NetworkManager can return to the setup hotspot if the saved network is unavailable. Give guests the Wi-Fi join code separately from their Photobox invitation. The two QR codes do different jobs, even when they are displayed next to each other.

The Pi does not need internet access for local photo capture and downloads. Internet-dependent sharing is outside this setup flow.

## Invite guests

1. From the administrator page, create a guest invitation. Invitations expire and can be revoked.
2. Show the guest invitation QR only to people who should join the booth. Do not confuse it with the Wi-Fi join QR.
3. Guests first connect to venue Wi-Fi or the Pi hotspot, whichever can reach the booth, and then scan the invitation.
4. One guest phone controls an active session. Other paired phones can watch and review previews but cannot operate the controls or download photos during capture. After the session completes, paired guests with its gallery link or QR can view and download its photos. The controller can be replaced after 60 seconds without activity.
5. Guest access expires after 12 hours by default until event-based expiry is implemented.

Photobox keeps guest and administrator access separate. Guest credentials are revocable and are not displayed in normal URLs. The planned browser credential is held in an HTTP-only cookie; on an HTTPS connection it is also marked secure.

After a session completes, Photobox creates a vertical photo strip without altering the original photos and shows a session gallery link and QR. Only people who have paired with the booth can open it. The QR points to that one session and does not provide a session-list or event-wide gallery. A paired guest can request an animated GIF. Photobox uses up to 8 recent live-preview frames, sampled at no more than 4 frames per second, when enough are available; otherwise it makes the GIF from the captured still photos. GIF frames are limited to 640×640 pixels and the output to 10 MB. The gallery reports if encoding fails.

An operator may configure a local transparent PNG overlay for each strip photo slot by setting `PHOTOBOX_STRIP_OVERLAY` to its file path before starting Photobox. The current layout requires a 360x480 PNG with transparent pixels and a maximum file size of 5 MB. Photobox rejects invalid overlays at startup; there is no guest upload or frame editor.

## If the setup PIN is lost

The PIN cannot be retrieved from the Pi because only its hash is stored. A remote guest invitation cannot reset or reveal it. The current image disables SSH, and there is no documented, tested PIN recovery procedure. Do not delete files or try an unverified reset command. Preserve the microSD card and photos, then ask the project maintainer for a recovery procedure before making changes. Reflashing an image erases the selected card and may erase photos and other data stored on it.

## If setup does not work

- **The Pi network is missing:** check power, wait for startup, and confirm the matching generic image was written to the intended card and `photobox-device.json` was copied to the top level of its boot partition. Use Ethernet or the documented local recovery process if available.
- **The phone says there is no internet:** while using the Pi hotspot, choose to stay connected. The local page does not require internet.
- **The status page does not open:** make sure the phone is still on the Pi or venue network. On the setup hotspot, try `http://10.42.0.1:8000` if `photobox.local` does not resolve. On venue Wi-Fi, use the IP address shown on the admin page or the venue router’s device list.
- **The setup PIN is rejected:** check for mistyped digits and whether the PIN was already used. Repeated attempts are rate-limited. Use local recovery if it has been consumed or lost.
- **Guests can open the page but cannot pair:** check that their guest invitation has not expired or been revoked, and that they joined a network that can reach this Pi.
- **A camera is not available:** the booth should stay on its status page and remain configurable. The host can fix or replace the camera without losing the setup connection.

This guide must be updated alongside implementation. Remove the planned-workflow notice only after the image provisioning, hotspot, first-admin claim, guest pairing, and recovery paths have all been tested on the supported Pi setup.

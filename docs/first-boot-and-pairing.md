# First Boot and Pairing

> **Status:** Phone pairing, the local one-time PIN command, a minimal stage-1-based Raspberry Pi OS image workflow, Linux-based per-device image provisioning, setup hotspot configuration, and admin-controlled venue Wi-Fi setup are implemented. The image and network paths have not yet been validated on physical Pi hardware.

Maintainers: the physical acceptance procedure is in [Milestone 2 Hardware Validation](hardware-validation-m2.md). Do not mark the setup flow complete until that checklist passes on the supported Pi/OS.

This guide is for someone setting up a Photobox without needing to know Linux networking or security terminology. It explains what the computer creates, what to put on the Pi, and what the different codes are for.

## Choose a setup path

**Already have Photobox running on a computer?** Use the [local-host steps](#available-now-local-pairing-on-an-installed-host). The computer and phone must already be on a network that can reach each other. This path does not create a hotspot.

**Setting up a Raspberry Pi?** Continue with [Prepare one Pi](#prepare-one-pi). You need a Linux computer to provision the image, a microSD card and reader, a way to flash an image, the Wi-Fi country code for the Pi's location, and the credentials for an optional venue Wi-Fi network. The first-boot and network features are implemented but have not yet passed physical hardware validation; use a test Pi, disposable card, and isolated network.

At a glance, the Pi path is: obtain and verify the generic image, create a private per-device image and credentials, flash that image, connect a phone to the Pi hotspot, claim admin access with the one-time PIN, and optionally configure venue Wi-Fi. Guest invitation is a separate step after admin setup.

These are two different operations: **joining Wi-Fi connects a device to the Pi’s network; accepting an invitation gives that device guest access to Photobox.**

## Available now: local pairing on an installed host

This is the development flow for an already-installed host. Network management requires a provisioned Pi image:

1. Install Photobox on a host and choose a data directory. Keep the same `PHOTOBOX_DATA_DIR` for the setup command and daemon if you override its default.
2. Run `photobox-setup-pin` in a trusted terminal. It prints a random 6-digit PIN once and stores only a slow hash in `pairing.sqlite3`. Record the PIN privately; the command refuses to replace it after setup is initialized.
3. Start `photobox` and open its address from a phone or laptop already on a network that can reach the host.
4. Enter the PIN to claim admin access. From the admin page, create a guest invitation QR or copy its short-lived link. Guests must already be on a reachable network before they scan/open the invitation.
5. Guests can view the active session; one phone controls it. The admin can revoke guest access from the paired-phone list.

The command does not create an SD-card image, configure a Wi-Fi password, start an access point, or connect the Pi to venue Wi-Fi. Do not assume a headless Pi can be reached over Wi-Fi until those networking pieces are implemented.

For maintainers preparing a per-device image, `photobox-provision --output-dir <new-directory>` creates the private credential bundle. To build an image, add `--base-image <image.img.xz> --wifi-country <ISO-country-code>`. The image installs the setup hotspot profile and regulatory country. An admin can configure a WPA-Personal venue network from the admin page; NetworkManager verifies a DHCP address and gateway before the setup hotspot is disabled. A failed connection leaves the setup hotspot as the fallback. Enterprise Wi-Fi and captive-portal login are not supported.

## Three codes, three purposes

`photobox-setup-pin` initializes an already-installed host. `photobox-provision --base-image <image.img.xz> --wifi-country <ISO-country-code> --output-dir <private-directory>` creates a per-device `.img` from the generic minimal Raspberry Pi OS image. Image provisioning currently requires Linux and may request `sudo` access to loop devices and the image filesystem.

- **Wi-Fi join code:** contains the visible network name and Wi-Fi password. It lets a phone or laptop connect to the Pi’s network. It does not sign the person in to Photobox.
- **Setup PIN:** a unique, one-time 6-digit number for the first administrator claim. It is not the Wi-Fi password and is not shared with guests. The local provisioning tool shows it when preparing that Pi’s image. The Pi stores only a hash and invalidates the PIN after a successful claim.
- **Guest invitation QR:** a short-lived invitation created by the administrator. It pairs one guest browser with the booth. It is not an administrator credential and does not contain the Wi-Fi password.

Do not combine these codes or post them in a public place. A hidden Wi-Fi name would not make the network secure; use the unique Wi-Fi password and separate Photobox credentials instead.

## Prepare one Pi

### 1. Get the generic image

The image is a minimal 64-bit Raspberry Pi OS image with Photobox installed. It is generic: it does not yet contain the Wi-Fi credentials or setup PIN for your device.

- For an alpha, beta, or release-candidate build, download the `.img.xz` image, `photobox-provision.pyz`, and `SHA256SUMS` from that GitHub prerelease.
- For a workflow build, open the repository's **Actions** tab, select a successful **Build Raspberry Pi image** run, and download its `photobox-raspios-arm64` artifact. GitHub downloads this artifact as a ZIP; extract it before continuing. It contains the image, the standalone provisioner, and their checksums. The artifact is retained for 30 days.

Keep the image, provisioner, and checksum file together. From that directory, verify the downloads before using them:

```sh
sha256sum --check SHA256SUMS
xz --test photobox*.img.xz
```

The checksum command should report `OK`; the archive test should exit without an error. If the artifact has a different image filename, use that exact filename in the `xz` command. Do not continue if verification fails.

### 2. Get the provisioning tool

The `photobox-provision.pyz` file is a self-contained Python tool included with the image download. It contains the provisioning code and its QR-code library, so you do not need to download the project source, install Photobox, or create a virtual environment. On the trusted Linux computer that will prepare the card, check that Python 3.11 or newer is available:

```sh
python3 --version
python3 photobox-provision.pyz --help
```

The computer must also have `losetup`, `lsblk`, `udevadm`, `mount`, and `install`. Image setup uses loop devices and mounts the image filesystem; the command may ask for `sudo` permission. Keep the computer and its terminal private while the PIN and Wi-Fi password are displayed.

### 3. Create per-device credentials and image

Choose a new, empty output directory for this Pi. The provisioner will not overwrite files in a non-empty directory. Replace the image path with the downloaded `.img.xz`, and replace `GB` with the two-letter ISO country code where the Pi will operate:

```sh
python3 "$HOME/Downloads/photobox-provision.pyz" \
	--base-image "$HOME/Downloads/photobox.img.xz" \
	--wifi-country GB \
	--output-dir "$HOME/photobox-device-setup"
```

The command creates `photobox-device.img`, `device.json`, and `wifi-join.svg` in that directory. It prints the device's Wi-Fi name, Wi-Fi password, and one-time 6-digit setup PIN. Save the PIN privately; it cannot be displayed again. The image contains the PIN hash, not the PIN itself. The command also makes the output directory and files owner-only on Linux.

Open `wifi-join.svg` in a browser to display or print the Wi-Fi join QR.

Do not omit `--base-image`: without it, the command only creates a credential bundle and does not produce a bootable image. Do not omit `--wifi-country` when building an image. If provisioning fails after creating files, preserve any useful error details but start again with a different empty output directory rather than mixing credentials from attempts.

Keep the image and credential bundle private. Do not commit them, attach them to a public issue, put them in shared CI artifacts, or paste the printed secrets into a chat. The Wi-Fi QR is for joining the Pi's network; the setup PIN is for the first admin claim.

### 4. Flash the image and boot

Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or use another image writer that supports a custom image. In Imager, choose **Use custom** and select `photobox-device.img` in the private output directory, then select the intended microSD card. **Writing the image erases the selected card. Confirm the card's device and capacity before starting.** Do not add a separate Wi-Fi configuration in the imaging tool; the per-device image already includes the setup hotspot configuration.

When writing finishes, eject the card safely, put it in the Pi, connect the camera, and power on. The Pi advertises the unique visible Wi-Fi name printed by the provisioner. The image advertises `photobox.local` on supported local networks; while connected directly to the setup hotspot, `10.42.0.1` is the fallback address.

The image contains the PIN hash and Wi-Fi settings in a Photobox-service-owned, mode-0600 configuration file, plus a root-owned NetworkManager setup profile. The Wi-Fi country is applied before NetworkManager starts. The image advertises the hostname `photobox.local`; a direct setup-hotspot address remains available if a phone does not resolve it.

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

- **The Pi network is missing:** check power, wait for startup, and confirm the per-device image was written to the intended card. Use Ethernet or the documented local recovery process if available.
- **The phone says there is no internet:** while using the Pi hotspot, choose to stay connected. The local page does not require internet.
- **The status page does not open:** make sure the phone is still on the Pi or venue network. On the setup hotspot, try `http://10.42.0.1:8000` if `photobox.local` does not resolve. On venue Wi-Fi, use the IP address shown on the admin page or the venue router’s device list.
- **The setup PIN is rejected:** check for mistyped digits and whether the PIN was already used. Repeated attempts are rate-limited. Use local recovery if it has been consumed or lost.
- **Guests can open the page but cannot pair:** check that their guest invitation has not expired or been revoked, and that they joined a network that can reach this Pi.
- **A camera is not available:** the booth should stay on its status page and remain configurable. The host can fix or replace the camera without losing the setup connection.

This guide must be updated alongside implementation. Remove the planned-workflow notice only after the image provisioning, hotspot, first-admin claim, guest pairing, and recovery paths have all been tested on the supported Pi setup.

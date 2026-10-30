# First Boot and Pairing

> **Status:** Phone pairing, the local one-time PIN command, a minimal Raspberry Pi OS Lite image build workflow, Linux-based per-device image provisioning, setup hotspot configuration, and admin-controlled venue Wi-Fi setup are implemented. The image and network paths have not yet been validated on physical Pi hardware.

Maintainers: the physical acceptance procedure is in [Milestone 2 Hardware Validation](hardware-validation-m2.md). Do not mark the setup flow complete until that checklist passes on the supported Pi/OS.

This guide is for someone setting up a Photobox without needing to know Linux networking or security terminology. It explains what the computer creates, what to put on the Pi, and what the different codes are for.

## The short version

1. Download the generic Raspberry Pi OS Lite image artifact from the image-build workflow.
2. On Linux, use the local image-provisioning tool to make a copy for one specific Pi. It creates that Pi’s Wi-Fi details and one-time setup PIN.
3. Write the per-Pi image to a microSD card and put it in that Pi.
4. Join the visible Wi-Fi network created by the Pi using the Wi-Fi QR code or the printed details.
5. Open the local Photobox page and enter the setup PIN to claim the booth as its first administrator.
6. Connect the Pi to venue Wi-Fi if available. The setup network turns off once venue Wi-Fi works; if it cannot connect, the Pi network remains available.
7. From the admin phone, create a separate guest invitation QR. Guests join a network that can reach the Pi, then scan the invitation.

These are two different operations: **joining Wi-Fi connects a device to the Pi’s network; accepting an invitation gives that device guest access to Photobox.**

## Available now: local pairing on an installed host

This is the development flow for an already-installed host. Network management requires a provisioned Pi image:

1. Install Photobox on a host and choose a data directory. Keep the same `PHOTOBOX_DATA_DIR` for the setup command and daemon if you override its default.
2. Run `photobox-setup-pin` in a trusted terminal. It prints a random 10-digit PIN once and stores only a slow hash in `pairing.sqlite3`. Record the PIN privately; the command refuses to replace it after setup is initialized.
3. Start `photobox` and open its address from a phone or laptop already on a network that can reach the host.
4. Enter the PIN to claim admin access. From the admin page, create a guest invitation QR or copy its short-lived link. Guests must already be on a reachable network before they scan/open the invitation.
5. Guests can view the active session; one phone controls it. The admin can revoke guest access from the paired-phone list.

The command does not create an SD-card image, configure a Wi-Fi password, start an access point, or connect the Pi to venue Wi-Fi. Do not assume a headless Pi can be reached over Wi-Fi until those networking pieces are implemented.

For maintainers preparing a per-device image, `photobox-provision --output-dir <new-directory>` creates the private credential bundle. To build an image, add `--base-image <image.img.xz> --wifi-country <ISO-country-code>`. The image installs the setup hotspot profile and regulatory country. An admin can configure a WPA-Personal venue network from the admin page; NetworkManager verifies a DHCP address and gateway before the setup hotspot is disabled. A failed connection leaves the setup hotspot as the fallback. Enterprise Wi-Fi and captive-portal login are not supported.

## Three codes, three purposes

`photobox-setup-pin` initializes an already-installed host. `photobox-provision --base-image <image.img.xz> --wifi-country <ISO-country-code> --output-dir <private-directory>` creates a per-device `.img` from a generic Raspberry Pi OS Lite image. Image provisioning currently requires Linux and may request `sudo` access to loop devices and the image filesystem.

- **Wi-Fi join code:** contains the visible network name and Wi-Fi password. It lets a phone or laptop connect to the Pi’s network. It does not sign the person in to Photobox.
- **Setup PIN:** a unique, one-time 10-digit number for the first administrator claim. It is not the Wi-Fi password and is not shared with guests. The local provisioning tool shows it when preparing that Pi’s image. The Pi stores only a hash and invalidates the PIN after a successful claim.
- **Guest invitation QR:** a short-lived invitation created by the administrator. It pairs one guest browser with the booth. It is not an administrator credential and does not contain the Wi-Fi password.

Do not combine these codes or post them in a public place. A hidden Wi-Fi name would not make the network secure; use the unique Wi-Fi password and separate Photobox credentials instead.

## Prepare one Pi

1. Download the generic `.img.xz` artifact built by the project’s image workflow. It contains Raspberry Pi OS Lite and Photobox software, but no per-device credentials. The workflow currently publishes an artifact, not a release download.
2. On a trusted Linux computer, run `photobox-provision --base-image <image.img.xz> --wifi-country <ISO-country-code> --output-dir <new-private-directory>` for the Pi you are preparing. Use the country where the Pi will operate. It creates a **per-device `.img` image**, a visible unique Wi-Fi name, a random Wi-Fi password, and a unique one-time 10-digit setup PIN. The tool displays the PIN once; write it down and keep it private. It requires loop-device and mount tools and may ask for `sudo`. Follow the tool’s instructions for saving or printing the Wi-Fi join code.
3. Keep the per-device image and codes together only while preparing that Pi. Do not commit them to Git, upload them to a shared CI artifact, or paste them into a public issue or chat. The Wi-Fi password, setup PIN, and guest invitation are different secrets.
4. Write the per-device image to the Pi’s microSD card with the operating-system imaging tool recommended by the project. **Writing an image erases the selected card.** Double-check the selected drive before confirming.
5. Put the card in the Pi, connect the camera and power, then start the Pi. The setup network has a visible name so it is easy to find; hiding it would not prevent discovery or unauthorized access.

The image contains the PIN hash and Wi-Fi settings in a Photobox-service-owned, mode-0600 configuration file, plus a root-owned NetworkManager setup profile. The Wi-Fi country is applied before NetworkManager starts. The image advertises the hostname `photobox.local`; a direct setup-hotspot address remains available if a phone does not resolve it.

## Claim the booth as administrator

1. On a phone or laptop, scan the Wi-Fi join code or select the printed network name and enter its password. The setup network may say “No internet”; that is expected while connected directly to the Pi. Choose to remain connected.
2. Open `http://photobox.local:8000`. If the phone cannot resolve that name while connected to the setup hotspot, use `http://10.42.0.1:8000`.
3. Enter the one-time setup PIN from the provisioning step. The first successful claim makes this browser the booth administrator. The PIN is then invalid and cannot be reused.
4. Confirm the camera and storage status. The admin page is separate from the guest controller.

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

After a session completes, Photobox creates a vertical photo strip without altering the original photos and shows a session gallery link and QR. Only people who have paired with the booth can open it. The QR points to that one session and does not provide a session-list or event-wide gallery.

## If the setup PIN is lost

The PIN cannot be retrieved from the Pi because only its hash is stored. Use local administrative access, such as the documented SSH recovery command, to generate a replacement or reprovision the Pi. A remote guest invitation cannot reset or reveal the administrator PIN.

Do not improvise a factory reset or delete the data directory: recovery commands must be documented and tested before this section is considered complete. Back up photos before reprovisioning; writing an image erases the selected microSD card.

## If setup does not work

- **The Pi network is missing:** check power, wait for startup, and confirm the per-device image was written to the intended card. Use Ethernet or the documented local recovery process if available.
- **The phone says there is no internet:** while using the Pi hotspot, choose to stay connected. The local page does not require internet.
- **The status page does not open:** make sure the phone is still on the Pi or venue network. On the setup hotspot, try `http://10.42.0.1:8000` if `photobox.local` does not resolve. On venue Wi-Fi, use the IP address shown on the admin page or the venue router’s device list.
- **The setup PIN is rejected:** check for mistyped digits and whether the PIN was already used. Repeated attempts are rate-limited. Use local recovery if it has been consumed or lost.
- **Guests can open the page but cannot pair:** check that their guest invitation has not expired or been revoked, and that they joined a network that can reach this Pi.
- **A camera is not available:** the booth should stay on its status page and remain configurable. The host can fix or replace the camera without losing the setup connection.

This guide must be updated alongside implementation. Remove the planned-workflow notice only after the image provisioning, hotspot, first-admin claim, guest pairing, and recovery paths have all been tested on the supported Pi setup.

# First Boot and Pairing

> **Status:** Phone pairing and the local one-time PIN command are implemented for an already-installed host. Per-device image creation, Wi-Fi credential provisioning, Pi hotspot setup, and venue Wi-Fi configuration are still planned. The complete SD-card/hotspot workflow below is not available yet.

This guide is for someone setting up a Photobox without needing to know Linux networking or security terminology. It explains what the computer creates, what to put on the Pi, and what the different codes are for.

## The short version

1. Download the common Photobox system image. (Image publishing is not yet implemented.)
2. Use the planned local image-provisioning tool on your computer to make a copy for one specific Pi. It will create that Pi’s Wi-Fi details and one-time setup PIN.
3. Write the per-Pi image to a microSD card and put it in that Pi.
4. Join the visible Wi-Fi network created by the Pi using the Wi-Fi QR code or the printed details.
5. Open the local Photobox page and enter the setup PIN to claim the booth as its first administrator.
6. Connect the Pi to venue Wi-Fi if available. The setup network turns off once venue Wi-Fi works; if it cannot connect, the Pi network remains available.
7. From the admin phone, create a separate guest invitation QR. Guests join a network that can reach the Pi, then scan the invitation.

These are two different operations: **joining Wi-Fi connects a device to the Pi’s network; accepting an invitation gives that device guest access to Photobox.**

## Available now: local pairing on an installed host

This is the supported development flow until per-device images and hotspot setup exist:

1. Install Photobox on a host and choose a data directory. Keep the same `PHOTOBOX_DATA_DIR` for the setup command and daemon if you override its default.
2. Run `photobox-setup-pin` in a trusted terminal. It prints a random 10-digit PIN once and stores only a slow hash in `pairing.sqlite3`. Record the PIN privately; the command refuses to replace it after setup is initialized.
3. Start `photobox` and open its address from a phone or laptop already on a network that can reach the host.
4. Enter the PIN to claim admin access. From the admin page, create a guest invitation QR or copy its short-lived link. Guests must already be on a reachable network before they scan/open the invitation.
5. Guests can view the active session; one phone controls it. The admin can revoke guest access from the paired-phone list.

The command does not create an SD-card image, configure a Wi-Fi password, start an access point, or connect the Pi to venue Wi-Fi. Do not assume a headless Pi can be reached over Wi-Fi until those networking pieces are implemented.

## Three codes, three purposes

Current behavior: `photobox-setup-pin` initializes an already-installed host. The image-time provisioner described later is still planned.

- **Wi-Fi join code:** contains the visible network name and Wi-Fi password. It lets a phone or laptop connect to the Pi’s network. It does not sign the person in to Photobox.
- **Setup PIN:** a unique, one-time 10-digit number for the first administrator claim. It is not the Wi-Fi password and is not shared with guests. The local provisioning tool shows it when preparing that Pi’s image. The Pi stores only a hash and invalidates the PIN after a successful claim.
- **Guest invitation QR:** a short-lived invitation created by the administrator. It pairs one guest browser with the booth. It is not an administrator credential and does not contain the Wi-Fi password.

Do not combine these codes or post them in a public place. A hidden Wi-Fi name would not make the network secure; use the unique Wi-Fi password and separate Photobox credentials instead.

## Prepare one Pi

1. Download the generic image built and tested by the project. This image is the base operating system and Photobox software; it does not contain a shared admin PIN.
2. On a computer you trust, run the local provisioning tool for the Pi you are preparing. It creates a **per-device image**, a visible unique Wi-Fi name, a random Wi-Fi password, and a unique one-time 10-digit setup PIN. The tool displays the PIN once; write it down and keep it private. Follow the tool’s instructions for saving or printing the Wi-Fi join code.
3. Keep the per-device image and codes together only while preparing that Pi. Do not commit them to Git, upload them to a shared CI artifact, or paste them into a public issue or chat. The Wi-Fi password, setup PIN, and guest invitation are different secrets.
4. Write the per-device image to the Pi’s microSD card with the operating-system imaging tool recommended by the project. **Writing an image erases the selected card.** Double-check the selected drive before confirming.
5. Put the card in the Pi, connect the camera and power, then start the Pi. The setup network has a visible name so it is easy to find; hiding it would not prevent discovery or unauthorized access.

The local provisioning tool and exact supported image-writing instructions are implementation deliverables. Until they exist, this setup flow is not available.

## Claim the booth as administrator

1. On a phone or laptop, scan the Wi-Fi join code or select the printed network name and enter its password. The setup network may say “No internet”; that is expected while connected directly to the Pi. Choose to remain connected.
2. Open the Photobox status page using the address provided by the provisioning instructions. The planned default is `http://photobox.local`; a direct local address must be available as a fallback if the phone cannot resolve that name.
3. Enter the one-time setup PIN from the provisioning step. The first successful claim makes this browser the booth administrator. The PIN is then invalid and cannot be reused.
4. Confirm the camera and storage status. The admin page is separate from the guest controller.

The Pi stores only a hash of the setup PIN. Failed claims are rate-limited. Never send the PIN as part of a URL or guest QR code.

## Connect to the venue network

From the administrator page, select the venue Wi-Fi and enter its password. If the Pi joins successfully and a phone on that network can reach it, the temporary setup hotspot turns off. Guests can use the venue Wi-Fi to reach Photobox.

If venue Wi-Fi is unavailable or the Pi cannot connect, its visible hotspot remains available during the event. Give guests the Wi-Fi join code separately from their Photobox invitation. The two QR codes do different jobs, even when they are displayed next to each other.

The Pi does not need internet access for local photo capture and downloads. Internet-dependent sharing is outside this setup flow.

## Invite guests

1. From the administrator page, create a guest invitation. Invitations expire and can be revoked.
2. Show the guest invitation QR only to people who should join the booth. Do not confuse it with the Wi-Fi join QR.
3. Guests first connect to venue Wi-Fi or the Pi hotspot, whichever can reach the booth, and then scan the invitation.
4. One guest phone controls an active session. Other paired phones can watch the active session and review photos but cannot operate the controls or download those images. The controller can be replaced after 60 seconds without activity.
5. Guest access expires after 12 hours by default until event-based expiry is implemented.

Photobox keeps guest and administrator access separate. Guest credentials are revocable and are not displayed in normal URLs. The planned browser credential is held in an HTTP-only cookie; on an HTTPS connection it is also marked secure.

## If the setup PIN is lost

The PIN cannot be retrieved from the Pi because only its hash is stored. Use local administrative access, such as the documented SSH recovery command, to generate a replacement or reprovision the Pi. A remote guest invitation cannot reset or reveal the administrator PIN.

Do not improvise a factory reset or delete the data directory: recovery commands must be documented and tested before this section is considered complete. Back up photos before reprovisioning; writing an image erases the selected microSD card.

## If setup does not work

- **The Pi network is missing:** check power, wait for startup, and confirm the per-device image was written to the intended card. Use Ethernet or the documented local recovery process if available.
- **The phone says there is no internet:** while using the Pi hotspot, choose to stay connected. The local page does not require internet.
- **The status page does not open:** make sure the phone is still on the Pi or venue network. Try the direct local address supplied by the provisioning instructions if `photobox.local` does not resolve.
- **The setup PIN is rejected:** check for mistyped digits and whether the PIN was already used. Repeated attempts are rate-limited. Use local recovery if it has been consumed or lost.
- **Guests can open the page but cannot pair:** check that their guest invitation has not expired or been revoked, and that they joined a network that can reach this Pi.
- **A camera is not available:** the booth should stay on its status page and remain configurable. The host can fix or replace the camera without losing the setup connection.

This guide must be updated alongside implementation. Remove the planned-workflow notice only after the image provisioning, hotspot, first-admin claim, guest pairing, and recovery paths have all been tested on the supported Pi setup.

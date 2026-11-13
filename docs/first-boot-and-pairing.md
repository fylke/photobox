# First Boot and Pairing

> **Status:** First boot setup, Wi-Fi, and phone pairing require physical Raspberry Pi validation. Use a disposable card and isolated test network. Maintainers: see [Hardware Validation](hardware-validation-m2.md).

You need a Raspberry Pi 4 or 5, a microSD card and reader, the [Photobox Web Installer](https://fylke.github.io/photobox/installer), a phone, and the Wi-Fi country where the Pi will operate.

## Write the image with the web installer

1. Open the [Photobox Web Installer](https://fylke.github.io/photobox/installer) in Chrome, Edge, or Brave
2. Select your Raspberry Pi model (4 or 5)
3. **Select the Wi-Fi country where the Pi will be used.** This sets the regulatory domain, needed even if you will not use venue Wi-Fi.
4. Connect your microSD card reader. **Writing erases the selected card. Confirm the selected device and capacity.**
5. Click **Write** and wait for the image to download and write to your card
6. Eject the card and insert it into the Pi
5. On a phone, join the open **Photobox Setup** Wi-Fi network. If the phone warns that there is no internet, stay connected. Open `http://photobox.local:8000` or, if that fails, `http://10.42.0.1:8000`.
6. Select **Set up this booth**, record the private Wi-Fi name and password shown, then select **Start private Wi-Fi**. Join that network, and reopen the same address in the same browser.
7. On the administrator page, confirm camera and storage status. Setup remains available without a camera, but sessions cannot start until one is available.

The temporary setup network is open: someone nearby could claim the booth first and observe setup traffic, including the private Wi-Fi password. Set up in a private location and do not enter venue Wi-Fi credentials until connected to the private network. The open network expires after 15 minutes; reboot the Pi to retry. If private Wi-Fi activation fails, reboot and reconnect to continue setup.

## Connect to venue Wi-Fi

After reconnecting to the private network, the administrator can optionally configure venue Wi-Fi. WPA-Personal is supported; enterprise Wi-Fi and captive portals are not. If connection fails, the private setup network remains available. Saved venue Wi-Fi is retried after reboot. Local capture does not require internet access.

## Invite guests

Create an invitation on the administrator page. Guests first join a network that can reach the Pi, then scan the invitation QR or open its link. The **Wi-Fi QR** connects them to a network; the **guest invitation** grants Photobox access. Invitations expire and guest access can be revoked.

## If setup does not work

- **Photobox Setup network missing:** confirm the Wi-Fi country was correctly selected during image write and check power and wait for first boot to finish.
- **Page does not open:** stay connected to the Pi network despite the “no internet” warning. Try `http://10.42.0.1:8000`.
- **Setup window expired:** reboot the Pi to reopen the temporary setup network.
- **Private network switch fails:** reboot, join the private network with the displayed credentials, and open the same Photobox address.
- **Guest cannot pair:** check network reachability and whether the invitation expired or was revoked.

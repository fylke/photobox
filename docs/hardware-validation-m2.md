# Milestone 2 Hardware Validation

> **Status:** Run this checklist only after the image provisioning, setup hotspot, and phone pairing paths are implemented. They are not all available in the current release. Mocked tests do not count as physical hardware validation.

This is the end-to-end acceptance run for a real Photobox Pi, webcam, and two phones. Keep each run on a disposable test event and a network you control.

## Equipment and preparation

- Raspberry Pi 4 or 5 with the supported Photobox OS image.
- V4L2-compatible USB/CSI webcam and any required camera permissions.
- A separate computer with the project’s local image-provisioning tool and an SD-card reader.
- Two phones or one phone and one laptop with current browsers.
- A disposable Wi-Fi network you administer, plus the Pi setup hotspot path.
- A blank/backup SD card and a way to restore the prior image.
- A fresh test data directory and no real guest photos.

Before testing, record the test ID, date, tester, Pi model, OS/image version and checksum, Photobox commit, camera model, and `ffmpeg` version. Do not record setup PINs, Wi-Fi passwords, guest tokens, cookie values, or identifying photos in the test report.

## Safety boundaries

- Use a new SD card or a verified backup. Writing an image erases the selected card; double-check its device name before flashing.
- Use a private, isolated test network. Do not port-forward the booth or test it on a public/shared Wi-Fi network.
- Do not use production Wi-Fi credentials or real guest data. Keep test credentials out of CI logs, screenshots, shell history, and issue attachments.
- Keep an Ethernet or local recovery path available during Wi-Fi changes. Stop the test if the Pi’s network changes affect other devices.
- The Pi must continue local capture without internet. Network loss must not corrupt photos or lock the host out of local recovery.

## Run the test

### A. Provision and first boot

- [ ] Build/test the generic base image in CI; record its artifact checksum.
- [ ] On the trusted provisioning computer, create a per-device image. Confirm it displays a unique 10-digit PIN once, creates a visible unique SSID and random Wi-Fi password, and does not send those secrets to CI or ordinary logs.
- [ ] Verify a second initialization attempt is refused. Verify the setup PIN is not stored in plaintext in the generated image/configuration.
- [ ] Flash the per-device image to the disposable SD card and boot the Pi. Confirm the SSID is visible and the advertised Wi-Fi join QR contains only Wi-Fi credentials.
- [ ] Join from phone A. Confirm the phone can reach the local status page while it reports “no internet”; confirm the URL contains no PIN or Wi-Fi password.

### B. Claim admin and configure network

- [ ] Enter an incorrect setup PIN. Confirm the claim fails without revealing whether other credentials are valid and repeated failures are rate-limited.
- [ ] Claim with the correct PIN from phone A. Confirm it becomes admin and receives an `HttpOnly`, `SameSite=Strict` cookie (`Secure` when HTTPS is used).
- [ ] Replay the setup PIN from another browser. Confirm it fails; restart the Pi and confirm the PIN is still consumed.
- [ ] Configure the disposable venue Wi-Fi. Confirm the Pi verifies reachability before disabling its setup AP.
- [ ] Disconnect venue Wi-Fi. Confirm the AP returns or remains available according to the agreed policy, the status page explains the network state, and local capture remains usable.
- [ ] Restore venue Wi-Fi and confirm AP shutdown does not interrupt an active capture.

### C. Pair a guest and exercise permissions

- [ ] From the admin page, create a guest invitation. Confirm its QR and copyable URL contain a short-lived invitation token in the URL fragment, not query/path data or logs.
- [ ] Join phone B to a network that can reach the Pi, then redeem the invitation. Confirm it receives a guest credential distinct from the admin credential.
- [ ] Reuse the invitation. Confirm redemption fails. Revoke phone B from the admin guest list and confirm the existing guest cookie stops working immediately.
- [ ] Confirm an expired invitation and an expired/revoked guest credential cannot be used.
- [ ] Start a session on phone A. Confirm phone B sees state updates but cannot start, advance, or download photos while A controls the session.
- [ ] Leave A idle for 60 seconds. Confirm B is offered takeover; claim it and confirm A becomes read-only. Verify an active controller cannot be displaced before the lease expires.
- [ ] Send a cross-origin mutation request from a separate test origin. Confirm it is rejected.

### D. Preview and capture

- [ ] Confirm MJPEG preview starts on the kiosk and phone and stops cleanly when each client leaves or a session begins.
- [ ] Confirm both browsers show the live preview from the physical camera. Record frame dimensions/rate and note excessive latency or dropped frames.
- [ ] Complete a multi-shot session from phone A, then repeat with phone B after takeover. Confirm countdown, review, and completion state stay synchronized.
- [ ] Confirm every original is saved and downloadable only by the controller; observers may review but cannot download another phone’s active-session photos.
- [ ] Disconnect the webcam during preview. Confirm the API remains responsive and the page shows an unavailable-preview state rather than hanging.
- [ ] Reboot the Pi with venue Wi-Fi unavailable. Confirm it returns to a recoverable status/pairing page and does not reuse a consumed setup PIN.

## Pass criteria

The run passes only when every applicable checkbox above passes on the supported image and hardware, and the tester records the results. A mocked camera, `TestClient`, or desktop browser test is useful evidence but does not replace the Pi/AP/camera checks. If an AP step is not yet implemented, mark the hardware run **blocked/incomplete**, not passed.

## Test record

```text
Test ID:
Date / tester:
Pi model / OS image checksum:
Photobox commit:
Camera model / ffmpeg version:
Network path tested (isolated test network only):
Result: pass / fail / blocked
Failed steps and issue links:
Sanitized logs or screenshots:
```

Remove secrets and guest-identifying content before attaching evidence to an issue or pull request. Keep the report with the release/implementation record; never commit the per-device image, setup PIN, Wi-Fi credentials, invitation token, or session photos.

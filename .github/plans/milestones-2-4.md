# Photobox Implementation Plan: Milestones 2–4

**Status (2026-10-30):** Milestone 1 is implemented in commit `10286a8`; physical webcam verification remains outstanding. Milestone 2 is in progress: setup PIN bootstrap, pairing/invitation API and UI, controller leases, and mock/V4L2 MJPEG preview are implemented. The per-device image builder, Wi-Fi credential provisioning, Pi hotspot, and venue Wi-Fi management are not implemented. Milestones 3–4 have not started.

This plan is the contributor-facing sequence through the media milestone. The user-facing, beginner-oriented setup workflow is in [First Boot and Pairing](../../docs/first-boot-and-pairing.md). Keep the two documents in sync as implementation decisions become code.

## Agreed decisions

- GitHub Actions builds and tests a generic base image. A local command on the installer’s trusted computer creates a per-Pi image and displays that device’s unique, one-time 10-digit setup PIN. Do not put per-device PINs in shared CI logs or artifacts.
- The local provisioner creates a visible, unique per-device setup SSID and random Wi-Fi password. SSID/password, admin setup PIN, and guest invitation are distinct credentials. A hidden SSID is not a security control.
- The initial admin connects to the Pi’s setup hotspot with a phone or laptop and claims the booth using the one-time setup PIN. Store only its hash on the Pi; rate-limit attempts and invalidate it after the first successful admin claim. Lost-PIN recovery requires local administrative access, such as SSH or reprovisioning.
- A paired admin creates separate, short-lived guest invitations. Guest credentials are revocable, stored as hashes, and delivered in an `HttpOnly`, `SameSite=Strict` cookie (also `Secure` under HTTPS); mutating requests validate their origin. Keep guest and admin capabilities separate.
- One guest phone controls an active session; other paired guests can observe its state and review images but cannot control or download them. Permit controller takeover after 60 seconds of inactivity. Default guest credentials to 12 hours until event-scoped expiry exists.
- When reachable venue Wi-Fi is configured, disable the setup AP. If it is unavailable, keep the visible Pi AP available for the event. Provide separate Wi-Fi-join and guest-invitation QR codes.
- Use the existing FastAPI service and static HTML/JavaScript UI. Start with HTTP MJPEG for preview. Keep AP configuration behind a NetworkManager adapter and out of request handlers.
- Use `gphoto2` as an isolated command-line integration for the initial Canon/Sony DSLR profiles. Keep Milestone 3 camera roles/bindings distinct from Milestone 6 primary/auxiliary screen classes.
- For Milestone 4, provide built-in strip layouts and locally supplied transparent PNG overlays; defer frame upload/editor UI. Build a session-scoped gallery and download QR; defer event-wide album browsing. Generate bounded GIFs from preview frames, falling back to timed still captures, and keep encoding off the capture request path.
- Ship a novice-first setup guide. Explain the terms and security boundaries plainly; never present planned functionality as available before it is implemented.

## Phase 0: Verify the Milestone 1 base

Run this on supported Linux/Pi hardware with a V4L2 webcam and `ffmpeg`, in parallel with hardware-independent Milestone 2 work:

1. Capture from the webcam through the daemon.
2. Confirm the JPEG preview renders in a browser.
3. Confirm the original photo and session metadata are saved.
4. Record the OS, camera, and `ffmpeg` versions and any limitations.

Do not claim physical camera support from mock/subprocess tests alone.

## Milestone 2: Phone access

1. **Provisioning contract:** build/test a generic image in CI; implement a local per-device provisioning command that emits a flashable image plus the unique one-time 10-digit PIN and Wi-Fi join information. Generate credentials with a cryptographically secure random source; hash the PIN before placing it on the Pi. Ensure secrets are not printed to CI logs, stored in the repository, or recoverable from ordinary application logs.
2. **Headless bootstrap and network mode:** bring up the visible setup AP; provide a status/pairing page reachable from a phone/laptop. Connect to configured venue Wi-Fi when available and disable the AP after verifying reachability. Otherwise retain the AP. Keep NetworkManager operations in a replaceable adapter and make failure/fallback state visible.
3. **Admin claim and guest pairing:** claim the booth with the one-time PIN, then allow the admin to issue short-lived guest invitations. Implement expiry, revocation, per-role authorization, rate limiting, and safe cookie/origin behavior before enabling guest control.
4. **Phone controller:** reuse the static frontend for phone-sized session start, state/review, and download flows. Enforce one controller per active session; observers remain read-only. Add 60-second inactivity takeover and 12-hour default guest expiry, both configurable.
5. **Preview:** extend the camera contract and mock camera for a bounded MJPEG stream. Add V4L2 preview via `ffmpeg`, with cleanup on disconnect and a clear no-preview fallback.
6. **QR onboarding:** show a Wi-Fi join QR separately from the guest invitation QR. The Wi-Fi QR contains only network credentials; the invitation QR contains only a short-lived claim URL/token. Never combine admin PIN, Wi-Fi password, and guest token in one URL/QR.

**Milestone 2 acceptance:** two different phones can reach the service headlessly, claim/pair with the appropriate role, and exercise controller/observer behavior; credentials expire/revoke as specified; the preview stream starts/stops cleanly; mocked AP behavior is tested; the novice setup guide matches the implemented flow. Verify Wi-Fi/AP behavior and phone browser behavior on the supported Pi/OS.

## Milestone 3: Capture quality

1. Add a camera registry with stable IDs, capabilities, availability, `preview`/`capture` roles, and minimal screen/client-to-camera bindings; persist only the required configuration.
2. Extend camera lifecycle/capability interfaces, then add a `gphoto2` driver for the supported Canon/Sony profiles. Preserve the mock and V4L2 implementations.
3. Implement the design’s §5.4 fallbacks: webcam capture when DSLR is unavailable; webcam/no-preview fallback when DSLR live view is unavailable; capture continues after preview loss; retry DSLR capture once, then use the latest preview frame and mark it low quality; setup/status remains available with no camera.
4. Keep bindings limited to camera selection. Do not implement primary/auxiliary screens, showcase behavior, or multi-camera screen layouts in this milestone.

**Milestone 3 acceptance:** unit/API tests cover role and binding selection, gphoto2 failures/disconnects, and each fallback including low-quality metadata. Manually verify the supported webcam and Canon/Sony profiles on hardware before advertising those profiles as validated.

## Milestone 4: Media

1. Extend storage to enumerate sessions/photos and save composed outputs beside immutable originals, with a JSON sidecar for relevant capture/media metadata.
2. Add Pillow for deterministic PNG-frame and strip composition. Support built-in strip layouts and locally supplied overlays selected through configuration; validate input dimensions and resource limits.
3. Add GIF generation from preview frames, with timed still captures as fallback. Enforce duration, FPS, and width server-side; process asynchronously/off the request path; reduce quality or return a clear media error without blocking still capture.
4. Add a session-scoped gallery endpoint/view and download QR. Reuse the individual-photo route, authorize access using the paired guest/session scope, and ensure other sessions are not exposed.
5. Update the operator guide with the actual media/gallery workflow; keep event-wide album browsing, voting, reporting, and moderation deferred.

**Milestone 4 acceptance:** tests prove originals remain unchanged; frame/strip output has deterministic dimensions and slot order; GIF limits and encoder failure behavior are enforced; gallery/download/QR access is session-scoped. Run the full test suite and Ruff, build a wheel and verify packaged assets, and smoke-test desktop/mobile browser flows.

## Documentation requirements

- Maintain [First Boot and Pairing](../../docs/first-boot-and-pairing.md) as the non-specialist operator guide. Include the steps to download/write an image, run local provisioning, identify the PIN versus Wi-Fi password versus guest invite, join the hotspot, claim admin, join venue Wi-Fi or stay on the Pi AP, and create guest invites.
- Explain what each QR code contains and who should scan it. Warn that flashing erases the selected SD card and that per-device credentials must not be shared or committed.
- Include recovery for a lost PIN, hotspot discovery, no-internet phone prompts, and unreachable status page. Clearly mark any step not yet implemented.
- Update this plan and the operator guide whenever an agreed decision changes; record unresolved decisions rather than silently changing defaults.

## Scope boundaries and risks

- Exclude Milestones 5–10 except features explicitly included above: hardware buttons/lights, screen showcase/classes, votes/reports, full phone setup/admin UI, log streaming, sharing, updates, printing, and event-wide phone albums.
- Treat the M1→M2→M3→M4 sequence as the integration order. Some edges are pragmatic rather than explicit design requirements; M1 hardware verification can run in parallel with M2 mock-driven work.
- Risks to manage: exposing bootstrap secrets in CI/artifacts/logs; AP setup requiring host networking privileges; cookie security on plain HTTP; camera subprocess lifecycle and device contention; gphoto2 model variation; image/GIF resource exhaustion; and lack of physical hardware in CI.

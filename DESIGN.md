# Photobox Design Document

Status: Draft. Derived from issues #1–#21 in `fylke/photobox`. Where an issue is vague, the open questions are listed in section 14.

## 1. Goals

A photo booth that runs on a Raspberry Pi with a camera attached.

- **Camera-agnostic:** works with a basic USB/CSI webcam and with a full DSLR/mirrorless camera.
- **Screen optional:** the normal setup has a local screen for previews, but everything must work headless.
- **Phone-friendly:** a phone can act as controller, preview screen, and configuration UI (#7, #12, #13).
- **Graceful degradation:** every optional capability (screen, flash/LEDs, buttons, DSLR, network, sharing services) has a fallback, and the booth never refuses to take photos because an optional part is missing.
- **Interoperable and installable:** the booth can be assembled from documented hardware profiles, and exposes a stable integration boundary for common home-automation systems.

Non-goals (for now): cloud hosting, multi-tenant SaaS, video recording beyond short GIFs.

## 2. Issue Traceability

| # | Requirement | Section |
|---|-------------|---------|
| 1 | Tie a screen to one or several cameras | 5.3, 6.2 |
| 2 | QR codes on screen: voting, reporting, downloading, configuration | 8.3, 6.6 |
| 3 | Add a frame to a set of photos; optionally pre-apply the frame | 7.3 |
| 4 | Use a webcam for photo preview when present | 5.1, 5.2 |
| 5 | LED light ramp or regular flash | 9.2 |
| 6 | Connect to common picture services (e.g. Instagram) | 10 |
| 7 | Set up the entire booth from a phone | 8.1, 8.2 |
| 8 | Debug logging, streamed to a phone | 11 |
| 9 | Optional hardware buttons and rotary encoder with assignable functions | 9.1 |
| 10 | Record animated GIFs, length limited by a configurable value | 7.2 |
| 11 | Countdown via LEDs | 9.3 |
| 12 | Control the whole booth from a phone by scanning a QR code | 8.2 |
| 13 | Use own phone as preview screen | 6.3 |
| 14 | Two screen classes: primary and auxiliary | 6.2 |
| 15 | Upvote and report pictures on an auxiliary screen | 6.5, 6.6 |
| 16 | Every screen beyond the first is auxiliary | 6.2 |
| 17 | Server management interface shows software versions and available updates | 8.4 |
| 18 | Resolve design comments: strips, admin access, phone album, upvotes, selfies, printing and priorities | 4.1, 6.2, 6.5, 6.8, 7.1, 8.5, 10, 14, 15 |
| 19 | View the current album on a phone, with swipe navigation and no timer | 6.7, 8.5 |
| 20 | Provide an IKEA-style setup guide for every hardware profile | 4.1 |
| 21 | Integrate with common home-automation protocols and products | 10.2 |

## 3. Architecture Overview

A single **server** process (the "booth daemon") runs on the Pi and owns all hardware. Everything else, including the local screen, phones, and the optional hardware controls, is a **client** that talks to the daemon over a local API. This keeps the headless case identical to the full case: the local screen is just another client.

```
                    +--------------------------------------+
                    |            Booth daemon (Pi)         |
 Camera drivers --> |  Capture   Session    Media          |
  (webcam, DSLR)    |  manager   state      pipeline       |
 GPIO (buttons,  -> |  Inputs    machine    (frame, GIF,   | --> Storage
  encoder)          |  Outputs              strip)         |
 LEDs / flash   <-- |  (lights)  Event bus  Share plugins  | --> Cloud services
                    |          HTTP + WebSocket API        |
                    +----------------+---------------------+
                                     |
        +----------------------------+--------------------------+
        |                            |                          |
  Local screen UI            Phone web UI (PWA)          Gallery / download
  (kiosk browser)      controller, preview, setup, logs     page
```

Rationale:
- One owner of the camera avoids contention (a DSLR cannot be opened by two processes).
- Web UIs for the screen and the phone share one codebase.
- The event bus decouples inputs (buttons, phone, touchscreen) from actions (take photo, change setting).

## 4. Hardware Profiles

The booth detects what is present at startup and on hot-plug, and runs in the best available profile. Profiles are not hard-coded modes.

| Profile | Camera | Screen | Extras | Behaviour |
|---------|--------|--------|--------|-----------|
| Minimal | USB/CSI webcam | none | none | Phone for preview and control; countdown via on-device indicator or audio |
| Standard | Webcam | HDMI/DSI screen | optional buttons | Local preview and touch/button control |
| Full | DSLR + webcam for preview | screen | LEDs/flash, buttons, encoder | Webcam preview, DSLR capture, light sync |
| Headless DSLR | DSLR | none | optional | Phone preview or no preview; control via button or phone |

Target hardware: Raspberry Pi 4 or 5 (Pi 3 supported at reduced preview resolution/frame rate).

### 4.1 Assembly and setup guide (#20)

The project ships an illustrated, step-by-step setup guide in the same order as the physical assembly. It is written for non-specialists and includes a parts checklist, cable and connector labels, mounting diagrams, a wiring diagram, software installation, first boot, pairing, and a test procedure. Each step has a checkbox and a visible expected result; optional steps are marked with the hardware profiles they support.

The guide has one common base path and profile-specific branches:

1. Mount the Pi, camera, screen, lights and controls, then connect power with the Pi powered off.
2. Select the profile (Minimal, Standard, Full or Headless DSLR) and follow only its camera, screen and lighting branch.
3. Install the supported OS image and Photobox package, start the first-run wizard, and connect by `photobox.local` or the printed setup QR code.
4. Run hardware detection and the guided test for camera capture, preview, screen, buttons, lights, storage and network.
5. Secure the enclosure and cables, record the device name, and run a test session before the event.

The guide explicitly covers both USB/CSI webcams and Canon/Sony A7-class cameras using gphoto2, including compatible cables, power requirements, camera mode, USB permissions, and troubleshooting. It never requires an optional component: omitted hardware is skipped and its fallback is shown.

## 5. Camera Subsystem

### 5.1 Camera abstraction

Each camera driver implements one interface:

- `capabilities()`: preview support, still capture, max resolution, controls (exposure, ISO, aperture, white balance), live-view support.
- `start_preview() / stop_preview()` returns an MJPEG or frame stream.
- `capture_still()` returns an image file/bytes.
- `capture_burst(n)` and `record_clip(duration)` (default falls back to repeated stills or preview frames).
- Hot-plug events: `attached` / `detached`.

Drivers:
- **V4L2/UVC webcam** (OpenCV or ffmpeg/v4l2).
- **Pi CSI camera** (libcamera/picamera2).
- **gphoto2** for DSLR/mirrorless (libgphoto2; PTP/USB).
- **Mock/test camera** (generates test patterns, used in dev and CI).

### 5.2 Roles and preview strategy (#4)

Each camera has one or more roles: `preview`, `capture`.

Preview source selection, in order of preference:

1. The capture camera's own live view, if it supports it (many DSLRs do via gphoto2, usually at low rate and with limitations while capturing).
2. A **separate webcam** assigned to `preview` (#4). The webcam sees roughly the same scene and is used so the DSLR is free for high-quality capture. Preview framing may differ from the final photo; the UI shows a crop guide.
3. The phone's own camera/screen as preview (#13, see 6.3).
4. No preview: countdown only (LEDs, audio, or on-screen text).

If a webcam is the only camera, it plays both roles: preview frames are the live stream, and the still is a full-resolution grab (or the last preview frame as a last resort).

### 5.3 Multiple cameras (#1)

The system supports N cameras. Screens (and phone clients) are **bound** to one or several cameras:

- A binding maps `screen → [camera ids]`. A screen bound to several cameras shows a grid or switchable view.
- A booth session names a **capture camera set**. Defaults to all cameras bound to the screen that started the session.
- If a bound camera is missing, the screen shows the remaining cameras and a warning. If none are available, it falls back to the status screen (section 6.4).
- The initial daemon persists camera role assignments and per-client camera ID bindings in `camera.json` under its data directory. Administrators read or update this configuration through `/api/cameras/config`; unknown camera IDs are rejected. Current bindings are camera-selection preferences for paired clients, not screen registrations or multi-camera layouts.

### 5.4 Camera fallbacks

| Situation | Fallback |
|-----------|----------|
| DSLR disconnects or battery dies | Switch to webcam capture, show a notice, retry the DSLR in the background |
| DSLR live view unavailable | Use webcam preview, or no preview |
| Webcam disconnects during preview | Show a still placeholder, keep capture working |
| DSLR capture fails | Retry once, then use the latest preview frame; flag the photo as "low quality" in metadata |
| No camera at all | Booth reports "no camera" on all clients, stays up for setup (#7) |

During an active capture, the daemon retries the selected camera once, then tries another available camera assigned the `capture` role for that paired client. The saved session camera ID changes to the camera that actually captured the photo. If alternate capture fails, the latest valid preview frame remains the low-quality fallback. Background device rediscovery and automatic switching back to a recovered DSLR are not yet implemented.

## 6. Display and Preview

### 6.1 Local screen

A kiosk browser (Chromium) opens the screen UI served by the daemon at `http://localhost`. It works on HDMI or the Pi touchscreen. The UI is touch-friendly but fully operable by hardware buttons (9.1).

### 6.2 Screen registration and classes (#1, #14, #16)

Screens register with the daemon, get an id, and are configured from the phone UI: name, class, bound cameras, layout (single, grid), idle content.

There are two screen classes:

| Class | Purpose | Shows |
|-------|---------|-------|
| **Primary** | Interaction with the booth | Preview before photos are taken (#14), result review, and the configuration interface when needed |
| **Auxiliary** | Showcase | Photos taken so far, as a cycling slideshow, plus upvote and report interaction (#15) |

Rules:
- There is exactly one primary screen at a time. It is the first screen to register (in practice the local kiosk screen).
- Any further screen connected is automatically auxiliary (#16). The admin may promote one to primary, which demotes the current primary.
- The first successfully paired local screen becomes primary only after the host confirms the pairing. Until then it is setup-only and cannot control capture. A primary change requires an authenticated admin action.
- Camera bindings (#1) matter mainly for the primary screen, as that is where preview is shown. Auxiliary screens do not show a live preview.
- A phone used as a preview screen (6.3) is a temporary primary-style preview client. It does not replace the primary screen.
- If the primary screen disappears, the booth keeps working through phone control (8.2) and hardware buttons. An auxiliary screen is never promoted automatically, and the admin is notified in the phone UI.
- With only one screen, it is primary. The showcase is then shown on it while idle, if enabled.

Admin access is separate from ordinary guest control. The setup page is reachable through a short-lived configuration QR code containing a one-time pairing token, or through a PIN entered on the local screen/status page. The first paired host is the initial administrator; it can issue expiring admin invitations as QR codes or one-time tokens to additional phones. Tokens are scoped to the event/booth, revocable, stored hashed, and never included in logs or normal guest URLs. Guest tokens cannot access setup, logs, deletion, updates or other sessions.

### 6.3 Phone as preview screen (#13)

A phone opens the preview page (via QR code or link) and receives the preview stream (MJPEG over HTTP, WebSocket frames, or WebRTC where latency matters). The phone is treated as another screen: it can be bound to cameras like any other screen. Preview works without internet because it uses the Pi's local network (see 12).

### 6.4 Headless / no screen

With no local screen, the daemon:
- runs without a display server,
- exposes a **status/pairing page** reachable over the network,
- shows how to connect via other means: a printed QR code from the installation, a known hostname (`photobox.local`), or LED/audio status codes.

### 6.5 Auxiliary showcase and upvoting (#15)

The auxiliary screen cycles through the photos taken so far (newest first, then a random or round-robin mix; configurable dwell time). Reported or hidden photos are never shown.

- **Upvote:** The primary method is a **physical button** on the auxiliary screen's location (GPIO, see 9.1), which upvotes the photo currently on screen. Only upvoting exists, there is no downvote. A QR-code upvote is possible but optional and off by default, since the photo will usually have cycled off before the phone is raised. If it is enabled, the QR link is photo-specific and valid for a short window.
- **Duplicates:** a vote button press is counted once per photo per short interval. Votes are anonymous, so unlimited button presses cannot be fully prevented. A cooldown limits abuse. Per-device limits apply to QR votes.
- **Fallback:** without a physical button, a touchscreen tap on the photo, or a QR vote, is used. Without any of these, the showcase is view-only.
- Votes are stored per photo and can rank a "most popular" view in the gallery.
- The showcase scheduler weights photos by their upvote count, so popular photos appear more often without excluding newer or unvoted photos. The weighting and minimum-new-photo rule are configurable.

The physical upvote button is an independent networked accessory, not a GPIO device attached to the display. Each button has a device identity and is paired to one auxiliary screen. Pressing it sends an authenticated `upvote(screen_id)` event to the booth API. The server resolves `screen_id` to the photo currently shown on that screen and records the vote; the button does not need to know the photo id. The auxiliary screen subscribes to the event bus and shows the animation only when its `screen_id` matches. A button can therefore be placed near any screen with a small network-capable controller, while the booth remains the single authority for cooldowns, vote storage and photo identity. Loss of the accessory or network changes only voting; the showcase continues.

Phone and QR upvotes include the explicit `photo_id` selected by the user, because the user controls which album photo is being viewed. The server checks that the photo belongs to the event before applying the same rate limits and vote rules.

### 6.6 Reporting flow (#2, #15)

Reporting is deliberately a multi-step flow, so it can't be done accidentally:

1. A guest triggers a report on the current photo (a dedicated button, or a touch control if available).
2. The showcase **pauses** on that photo and shows a **report QR code**. The pause lasts **1 minute** (configurable), after which the showcase resumes whether or not the QR was scanned.
3. Scanning the QR opens a page with a **required text field** asking the guest to give a reason for the report. The link remains valid after the showcase has resumed, so the guest can write the reason at their own pace (suggested expiry: 15 minutes, configurable).
4. A submitted report is stored with the reason and marked pending. By default a pending report hides the photo from the showcase and blocks auto-publishing (10) until an admin reviews it. This is configurable.
5. Every administrator receives the review notification. Any one administrator may dismiss the report or delete/hide the photo; no unanimous decision or second approval is required.

If a report is triggered but never completed, the photo is not hidden or flagged. Only one report flow can be active per auxiliary screen at a time, and further report triggers are ignored during the pause.

### 6.7 Phone album view (#19)

The guest gallery is available from the event QR code whether or not an auxiliary screen exists. It shows the current event album and the latest photo, with swipe/previous/next navigation through photos, upvote, download and report controls. Album navigation is user-driven and has no slideshow timer. A phone may remain on this view while the booth captures more photos; the client receives updates over WebSocket/SSE and keeps its current position unless the user chooses “latest”. Access is limited to the paired event token and the guest privacy rules in section 12.

### 6.8 Guest selfie uploads (#18)

Selfies are a separate, optional event feature rather than a replacement for the booth preview. A guest scans the event QR code, grants the browser camera permission, takes a selfie, reviews it, and submits it to the event album. The server validates type, size and image dimensions, strips metadata, applies the event's moderation/report rules, and marks the upload as guest-provided. Uploads are disabled by default, can be enabled per event by an admin, and never require the phone to become a capture camera for the booth.

## 7. Capture and Media Pipeline

### 7.1 Session state machine

```
Idle -> Armed (trigger received) -> Countdown -> Capture -> Review
     -> (repeat for set size) -> Compose -> Done/Share -> Idle
```

Triggers: touchscreen, phone, hardware button, keyboard, HTTP call. Timeouts return the booth to Idle if a user abandons a session.

A session has: a mode (`photo`, `strip`, `gif`), the number of shots, the countdown length, a frame/template, and the list of cameras. `strip` means one composed output image containing multiple separately captured photos arranged in ordered slots (typically a vertical or horizontal photobooth strip); it is not a video or a single camera burst. Each slot can have its own crop, and the originals remain available alongside the composed strip.

### 7.2 Animated GIFs (#10)

- Frames come from the preview stream (or burst captures) of the selected camera.
- Maximum length is configurable (`gif.max_seconds`, `gif.fps`, `gif.max_width`), enforced by the daemon regardless of what the client asks for.
- Encoding uses ffmpeg/Pillow. Runs in the background to keep the booth responsive. An optional MP4/WebP output is offered when GIF size is too large.
- Fallback: if the encoder is too slow (Pi 3), reduce resolution/fps automatically.

### 7.3 Frames and composition (#3)

- A **frame** (overlay/template) is a PNG with transparent areas or a layout (strip, grid) with slot definitions.
- Applied to a set of photos on the server (`area:server`), producing a composed image next to the originals. Originals are never modified.
- A locally supplied transparent PNG may be configured with `PHOTOBOX_STRIP_OVERLAY`. The current built-in vertical-strip layout applies it over each 360x480 photo slot; the daemon validates format, dimensions, transparency, and file size before use. Frame upload/editor UI remains deferred.
- **Pre-applied frame:** if the preview source supports overlays (the UI can draw the frame over the preview; some DSLRs/webcams can't), the preview shows the frame so the guest can position themselves. This is a UI overlay only; actual composition still happens server-side. If the active display cannot overlay (e.g. no screen), the step is skipped.
- Frames are managed (upload, select, set default) from the phone UI.

### 7.4 Storage

- Local directory (default `~/photobox/events/<event>/<session>/`), with originals, composed output, and a JSON sidecar (cameras used, timestamps, settings, share status).
- Optional external USB storage; fallback to SD card if it is missing. The booth warns on low disk space and can stop GIFs first.
- Events group sessions, so a party's output can be downloaded or deleted together.

## 8. Phone and Web Interfaces

### 8.1 Phone setup UI (#7)

A responsive web app (PWA) served by the daemon, covering the entire setup:

- Camera detection, role assignment, test shots
- Screen registration and binding (#1)
- Countdown length, mode defaults, GIF limits
- Frames and templates
- Hardware button / encoder mapping (9.1), LED configuration (9.2/9.3)
- Sharing service accounts (10)
- Network and Wi-Fi setup, event management
- Debug log viewer (11)
- Report review queue (6.6) and vote overview (6.5)
- Server management: versions and updates (8.4)

Everything the UI can do is also available as a config file (YAML) for users who prefer SSH, and a first-run wizard is shown if the booth has never been configured.

### 8.2 Phone as remote control (#12)

- The local screen (and the printed/pairing page for headless setups) shows a QR code with a URL and a one-time pairing token.
- Scanning opens the controller page: start a session, choose mode, see the preview (6.3), review/retake, share.
- The configuration (admin) QR code and the guest controller QR code are separate, with different permissions (see 12).
- Several phones may connect at once; the session state is shared, and only one phone controls an active session (others view).

### 8.3 QR codes on screen (#2)

The idle and result screens can show these QR codes, each individually enabled:

| QR | Target | Audience |
|----|--------|----------|
| Download | Gallery page for the current session/photo | Guests |
| Voting | Upvote the photo on an auxiliary screen. Optional, secondary to the physical button (6.5) | Guests |
| Reporting | Report form for a photo. Shown only after a report is triggered, with the showcase paused (6.6) | Guests |
| Configuration | Admin setup UI (#7), protected by token/PIN | Host |
| Control (#12) | Phone controller page | Guests/host |

Placement follows screen class: download, control and configuration QR codes belong on the primary screen. Voting and reporting belong on auxiliary screens. With no screen, the QR codes are available from the status page and may be printed or exported as PNGs from the setup UI.

### 8.4 Server management and updates (#17)

An admin-only page in the phone UI that shows:

- Booth software version, and the versions of key components: OS and kernel, Python runtime, web server, gphoto2/libgphoto2, ffmpeg, kiosk browser, and installed plugins/add-ons.
- Available updates for each, checked periodically (and on demand) when the network is reachable, with changelogs where available. Without a network it shows the installed versions and "unknown" for updates.

As an extra feature, updating can be started from the same page:
- Updates are **never applied automatically** and never while a session is in progress or an event is running (an "event mode" lock can postpone updates).
- Before an update, a configuration backup is taken. The booth software update is done with a rollback option to the previous version if the booth fails its health check after restart.
- OS packages are updated via the package manager, and the page reports whether a reboot is needed.
- If an update fails or the network is lost midway, the previous version stays active.
- Fallback: without the update feature (or for users who want full control), the page remains read-only and the same information is available from the CLI.

### 8.5 Phone album and guest access (#19)

The event QR code opens the album view (6.7) directly. Guests can swipe through the current album, upvote, download a permitted photo, or submit a report without needing an auxiliary screen. The same view is linked from the auxiliary and primary screens. It deliberately has no automatic timer: a phone user controls navigation, while a screen slideshow remains governed by the auxiliary-screen dwell setting.

### 8.6 Guest selfie uploads (#18)

Selfies are a separate, optional event feature rather than a replacement for the booth preview. A guest scans the event QR code, grants the browser camera permission, takes a selfie, reviews it, and submits it to the event album. The server validates type, size and image dimensions, strips metadata, applies the event's moderation/report rules, and marks the upload as guest-provided. Uploads are disabled by default, can be enabled per event by an admin, and never require the phone to become a capture camera for the booth.

## 9. Hardware I/O

### 9.1 Buttons and rotary encoder (#9)

Optional, via GPIO (gpiozero/libgpiod) and debounced. Each physical input emits an event (`press`, `long_press`, `rotate_cw`, `rotate_ccw`, `encoder_press`). The mapping `input → action` is configurable and has defaults:

- Button 1: start session
- Encoder rotate: change mode/frame, or countdown length
- Encoder press: confirm
- Long press: shutdown or reset the session

Actions come from the same action set as the touch and phone UIs. If no hardware is present, nothing changes; the actions remain available over the UI.

### 9.2 Lighting: LED ramp or flash (#5)

A `Light` interface with implementations:
- **LED ramp/strip:** PWM via GPIO or addressable LEDs (WS2812/NeoPixel), brightness controlled per phase (idle, countdown, capture).
- **Flash:** a hot-shoe/trigger signal fired through a relay/optocoupler or the DSLR's own flash (controlled by the camera).
- **Screen flash:** the screen turns white during capture. Used when no lights exist. Unavailable when headless.
- **None.**

The light is synchronised with capture: the ramp goes to full brightness (or the flash fires) just before the exposure. A configurable lead time compensates for the camera's latency. Exposure settings can be varied by light type (e.g. disable the DSLR's flash when an external one is in use).

### 9.3 LED countdown (#11)

Countdown output uses a `CountdownIndicator` abstraction with LED patterns (e.g. fill/blink/colour per second). Fallbacks, in order: LEDs, on-screen digits, audio beeps/speech, phone display/vibration. Multiple indicators may run at once.

## 10. Sharing and Integrations (#6, #21)

A plugin interface `SharePlugin` with `authorize()`, `publish(media, caption)`, and `status()`.

Planned/possible targets:
- Local gallery link and QR code download (always available, no internet needed)
- Email, and a messaging app or webhook
- Instagram and other social services
- Cloud storage (Google Photos, S3-compatible, Dropbox, ...)

Important constraints:
- Instagram's APIs limit automated publishing (a business/creator account is required, and rules change). The design treats such services as best-effort plugins and not as core features.
- Publishing is queued with retries. If the network is down, uploads wait and the booth continues taking photos. The user sees "queued" status.
- Posting is opt-in per session; the host can enable auto-publish for an event. A photo with a pending report (6.6) is held back from publishing.
- Credentials are stored on the Pi only and never logged.

### 10.1 Social sharing priority

The first version prioritises the local gallery, QR download, email and generic webhooks. Social publishing (including Instagram) is a later milestone and remains opt-in, best-effort and subject to each provider's current API and account requirements. Printing is also a possible future milestone, implemented as a queue of rendered media sent to a configured local/network printer; it is not required for the first release.

### 10.2 Home-automation integration (#21)

The daemon exposes an event and command adapter rather than coupling the core to one vendor. The initial adapters target **MQTT** (including Home Assistant discovery), **Home Assistant's REST/WebSocket API**, and **Webhooks** for products that support HTTP callbacks. Adapters are optional plugins and can be disabled completely.

Published state includes availability, current session state, camera/screen connectivity, current event, latest photo id, vote/report counts and update status. Events include `session.started`, `countdown.started`, `capture.completed`, `media.ready`, `report.created`, `session.finished` and `fault.changed`. Commands are deliberately limited to safe, authenticated actions such as start/stop session, set light scene, display a message and request a gallery link; destructive actions and admin/update operations are never exposed by default.

Each adapter has configurable credentials, an allowlist of commands, rate limits, retry/backoff and an offline queue. Payloads contain opaque photo/session ids and no credentials. The integration uses a versioned JSON schema so future protocol adapters can map the same events without changing capture behavior.

## 11. Debug Logging (#8)

- Structured logging with levels. Debug logging is off by default and is turned on from the phone UI or config.
- A **live log stream** is delivered to the phone through WebSocket/Server-Sent Events. Client-side filters by level and component are available.
- A ring buffer in memory retains recent logs, so a phone that connects late sees recent history.
- Persistent logs are written to disk with rotation. They can be downloaded as a bundle (logs + config with secrets redacted + hardware detection report).
- Fallback: without a phone, logs go to file and journald.

## 12. Networking, Security, and Privacy

- **Network modes:**
  1. Join existing Wi-Fi/Ethernet (preferred when available).
  2. If no known network is reachable, the Pi starts its own **access point** so phones can still connect for preview, control, and setup. Offline mode disables cloud sharing but nothing else.
  3. mDNS name (`photobox.local`) plus QR codes to avoid typing IPs.
- **Access levels:** `guest` (control a session, download own photos, upvote, report), `admin` (everything, including configuration, logs, deletion). Admin access requires a PIN or a one-time token via the configuration QR (#2), and tokens expire.
- Guest pages are rate-limited and should not expose other sessions' photos except via explicit event galleries.
- HTTPS is optional on a LAN. Browsers restrict some phone features (e.g. camera access for 6.3 where applicable) to secure contexts, so the booth can generate a self-signed or local certificate where needed.
- Privacy: photos stay local unless shared. Retention policy (auto-delete after N days) is configurable. Guests can delete their own photos right after a session.

## 13. Technology Choices (proposed)

| Concern | Choice | Why |
|---------|--------|-----|
| Daemon language | Python 3 | Mature Pi ecosystem (picamera2, gpiozero, gphoto2 bindings, Pillow) |
| API | FastAPI (HTTP + WebSocket/SSE) | Async, simple, typed |
| UI | Web app (TypeScript, light framework); served by the daemon | One codebase for the screen and phones |
| Kiosk | Chromium kiosk mode | Standard on Raspberry Pi OS |
| DSLR | libgphoto2 | Broad camera support |
| Image/GIF | Pillow, ffmpeg | Available on ARM |
| Config | YAML + web UI | Both headless and phone setup |
| Packaging | systemd service + install script (optionally Docker) | Starts on boot, restarts on failure |

These are proposals and can be revised before implementation.

## 14. Open Questions

1. **Resolved for v1:** certify Canon and Sony A7-class cameras first; broader gphoto2 coverage can follow.
2. **Resolved for v1:** a phone camera is used only for the separate guest-selfie feature (6.8/8.6), not as a booth capture camera or general preview source.
3. Which printer protocols and models should be prioritised when printing is scheduled for a future milestone? **Deferred.**
4. Which additional home-automation products should receive first-party adapters after MQTT, Home Assistant and webhooks? **Deferred.**
5. **Resolved:** use a one-minute showcase pause and a configurable 15-minute report-link expiry by default.
6. **Resolved:** updates may be applied only after an explicit admin action; they are never automatic.

## 15. Suggested Milestones

1. **Core:** daemon, camera abstraction with webcam and mock driver, session state machine, local storage, minimal screen UI.
2. **Phone access:** QR pairing, phone controller (#12), phone preview (#13), headless status page, AP fallback.
3. **Capture quality:** gphoto2 DSLR driver, webcam-as-preview (#4), camera/screen binding (#1), fallbacks from 5.4.
4. **Media:** frames and strips (#3), GIFs (#10), gallery and download QR (#2).
5. **Hardware:** buttons/encoder (#9), lights/flash (#5), LED countdown (#11).
6. **Screens and showcase:** primary/auxiliary classes (#14, #16), showcase slideshow, upvoting (#15), reporting flow and admin review (#15, #2).
7. **Setup and ops:** full phone-based setup (#7), debug log streaming (#8), version overview (#17), retention and backups.
8. **Operations and integrations:** publish the illustrated hardware setup guide, add MQTT/Home Assistant/webhook adapters, and expose the phone album as the default event landing page.
9. **Sharing and updates:** local gallery, generic webhooks and email first; social services later; then the update feature of #17 (read-only version display ships in milestone 7).
10. **Future hardware:** printing support and additional certified camera/printer integrations.

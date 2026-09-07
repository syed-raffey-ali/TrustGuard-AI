# TrustGuard AI — Android demo app

Scam-protection demo client (Kotlin + Jetpack Compose Material3) that talks to
the TrustGuard gateway over REST + WebSockets.

## Requirements

- Android Studio (Koala or newer) with SDK Platform 36 installed
- JDK 17 (bundled with recent Android Studio)
- A running TrustGuard gateway (default port 8080)

## Build & run

Option A — Android Studio:
1. `File ▸ Open...` and select this `apps/android` folder.
2. Let Gradle sync (wrapper generation is handled by the parent tooling; if
   prompted, use the IDE's Gradle wrapper).
3. Run the `app` configuration on an emulator or device.

Option B — command line:

```bash
cd apps/android
gradle :app:assembleDebug        # or ./gradlew :app:assembleDebug once a wrapper exists
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Configure the gateway URL

The gateway base URL is set per device in **Settings** (gear icon on the roster screen).

- **Emulator:** the host machine is reachable at `10.0.2.2`, so keep the default
  `http://10.0.2.2:8080`.
- **Physical devices:** use your laptop's LAN IP, e.g. `http://192.168.1.20:8080`
  (phone and laptop must be on the same Wi-Fi network). Find it with `ip addr`
  / `ifconfig`. Make sure the gateway listens on `0.0.0.0`, not just localhost.

## Two-device demo flow

1. On both devices/emulators: open the app, enter a display name, tap **Register**.
   The device ID is stored locally (DataStore).
2. Phone A (victim): on the roster, either pick Phone B from *Known devices* or
   type its device ID in the manual field.
3. Tap **Chat ▸** to start a chat session (or **Call ▸** for voice).
4. Phone B (scammer side): open **Director Mode**, choose a scenario script
   (`scenario_b_bank_otp` = flagship bank/OTP call+chat hybrid,
   `scenario_c_grooming` = romance/investment grooming chat), tap
   **Start scripted session**, then push scammer lines one by one with
   **Send next line**. Progress shows `k/n`.
5. Phone A shows:
   - chat bubbles; every **sent** message is scanned synchronously on-device by
     Tier-1 regex rules — hit chips appear inline under the bubble together
     with the measured scan time (<150 ms claim);
   - a pinned risk banner (score + colour strip: low green, medium yellow,
     high orange, critical red);
   - during calls: a persistent "This call is being analysed by TrustGuard AI"
     chip, and when the band reaches **critical** a full-screen overlay with
     safe actions (End Call / Freeze accounts (demo) / Report / Dismiss).

Voice calls stream 16 kHz mono PCM16 audio in ~100 ms chunks over the call
WebSocket; the microphone permission is requested on first call.

Pre-recorded director clips go in
`app/src/main/assets/director/clips/` as `line_01.wav`, `line_02.wav`, ... — see
the README.txt in that folder.

## Project layout

```
apps/android/
├── settings.gradle.kts / build.gradle.kts / gradle.properties
└── app/
    ├── build.gradle.kts                  AGP 8.5.2 · Kotlin 2.0.21 · Compose
    └── src/main/
        ├── AndroidManifest.xml           INTERNET + RECORD_AUDIO + POST_NOTIFICATIONS
        ├── assets/director/              scenario scripts + clip folder
        └── java/pk/trustguard/
            ├── app/                      MainActivity, screens, net, audio, data
            ├── tier1/Tier1Rules.kt       dependency-free on-device regex heuristics
            └── director/DirectorScripts.kt scripted-scenario loader
```

Routes: `register`, `roster`, `chat/{sessionId}/{peerId}`,
`call/{sessionId}/{peerId}`, `director`, `settings`.

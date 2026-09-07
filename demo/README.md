# TrustGuard AI Demo Gallery

This folder is the visual proof of the implemented prototype. The captures are grouped into dashboard evidence and Android client evidence. They are intentionally kept outside the runtime and source directories so the project remains easy to build.

## Demo narrative

The screenshots tell one story:

1. A user connects the Android client to the gateway on a local network.
2. The user enters a chat or call with a suspicious contact.
3. Fast Tier-1 checks appear immediately on the client.
4. Risk increases as the conversation requests account details, PINs, or OTPs.
5. The call screen explains the reason for the warning and offers safe actions.
6. The dashboard provides the investigation view: timeline, evidence, model race, provider health, and privacy boundaries.

## Web dashboard captures

### 1. Completed live transcript

![Completed live transcript](web/01-completed-live-transcript.png)

The dashboard is subscribed to a real gateway session. Three chat messages are visible, the timeline contains completed risk updates, the gauge shows `39/100 MEDIUM`, and the signal breakdown identifies OTP harvesting and bank impersonation.

### 2. Evidence history

![Evidence history](web/02-completed-evidence.png)

The Evidence panel turns the score into an auditable report. It shows score history, signal contribution, confidence, tier, quoted message evidence, message references, and occurrence counts.

### 3. Model Race

![Model Race](web/03-completed-model-race.png)

The Model Race panel shows a completed comparison cycle across configured providers. It makes latency and provider failures visible instead of hiding them behind one opaque answer.

### 4. Provider testing

![Provider test](web/04-providers-tested.png)

The provider registry shows configured endpoints, model names, provider kind, priority, masked key status, and the add/update form. The screenshot includes a completed provider test: `OK - 1056 ms - no signals found`.

### 5. Plain-text Paste Analyzer

![Plain text analysis](web/05-completed-plain-analysis.png)

A plain transcript is analyzed with Unknown Caller enabled. The completed result is `60/100 HIGH` and includes a safe action, evidence cards, model comparison summary, and parsed messages.

### 6. Privacy and consent

![Privacy principles](web/06-privacy-principles.png)

The Privacy panel explains the prototype's boundaries: app-owned sessions, no raw-audio persistence, no keys in the APK, visible analysis indication, fictional bank data, and explainable scoring.

### 7. WhatsApp-export Paste Analyzer

![WhatsApp analysis](web/07-completed-whatsapp-analysis.png)

A WhatsApp-export style transcript produces a completed `86/100 CRITICAL` result with safe actions, quoted evidence, model results, Tier-1 hits, and parsed messages. This is the strongest dashboard proof of the bank-impersonation plus OTP scenario.

## Android client captures

The supplied phone captures are ordered by the flow they demonstrate. The filenames are descriptive so reviewers can understand the gallery without opening every image first.

### Account and connectivity

<p align="center"><img src="phone/02-account-session-roster.jpeg" alt="Account session roster" width="220"></p>

The signed-in client establishes the user identity and local session context.

<p align="center"><img src="phone/03-gateway-settings-lan-ip.jpeg" alt="Gateway settings" width="220"></p>

The Settings screen shows the gateway URL configured to a server LAN address. Replace the example address with the IPv4 address of the computer running the gateway. For an emulator, use `http://10.0.2.2:8080`; for a physical phone, use `http://SERVER_LOCAL_IP:8080`.

<p align="center"><img src="phone/04-new-chat-roster.jpeg" alt="New chat roster" width="220"></p>

The roster exposes available demo contacts and their activity state.

<p align="center"><img src="phone/05-contacts-roster.jpeg" alt="Contacts roster" width="220"></p>

The contacts view shows the device-to-device demo topology used for chat and call testing.

### Chat protection

<p align="center"><img src="phone/01-chat-tier1-smoke-test.jpeg" alt="Tier-1 smoke test" width="220"></p>

A normal chat remains usable while the client displays the analysis indicator and the measured Tier-1 scan latency under the target budget.

<p align="center"><img src="phone/10-chat-account-request.jpeg" alt="Account request" width="220"></p>

An account-number request is marked inline, showing that the client gives feedback at message level rather than waiting for a final transaction.

<p align="center"><img src="phone/08-chat-account-suspicious.jpeg" alt="Suspicious account chat" width="220"></p>

The conversation begins to show suspicious-account language and the protected-chat state.

<p align="center"><img src="phone/09-chat-medium-risk.jpeg" alt="Medium chat risk" width="220"></p>

The risk state escalates to Medium as manipulation signals accumulate.

<p align="center"><img src="phone/07-chat-otp-signal.jpeg" alt="OTP chat signal" width="220"></p>

The OTP-oriented message is visible with on-device Tier-1 feedback. This is the critical precursor to the cross-channel call scenario.

<p align="center"><img src="phone/06-critical-chat-alert.jpeg" alt="Critical chat alert" width="220"></p>

The chat flow reaches a critical warning state, demonstrating the client-side alert surface.

### Call protection

<p align="center"><img src="phone/11-call-medium-warning.jpeg" alt="Medium call warning" width="220"></p>

The call screen keeps the analysis indicator visible and explains the first warning band.

<p align="center"><img src="phone/13-call-medium-warning-detail.jpeg" alt="Medium warning detail" width="220"></p>

A second Medium-state capture shows the warning reasons and live transcript context during the call.

<p align="center"><img src="phone/12-call-high-warning.jpeg" alt="High call warning" width="220"></p>

The call becomes High risk as requests for credentials and account information accumulate.

<p align="center"><img src="phone/15-call-high-alert.jpeg" alt="High scam alert" width="220"></p>

The High-risk call surface offers a clear action to end the call and shows why the user is seeing the warning.

<p align="center"><img src="phone/14-call-critical-alert.jpeg" alt="Critical call alert" width="220"></p>

The Critical state demonstrates the strongest intervention surface, including the persistent analysis indicator, evidence reasons, transcript context, and safe call controls.

## How to present the demo

Use the dashboard screenshots to explain the system architecture and evidence model. Use the Android screenshots to show that the protection experience is visible where the user actually makes the decision.

A strong live sequence is:

1. Open Settings and show the gateway URL.
2. Open the roster and start a chat.
3. Send an ordinary message and point out the fast Tier-1 timing badge.
4. Send account, PIN, urgency, and OTP language.
5. Show the Medium/High/Critical escalation.
6. Run the call scenario and show the persistent analysis indicator.
7. End in the dashboard Paste Analyzer and Evidence panels to explain the score.
8. Finish with Privacy to explain why the system is user-visible and server-side keys never enter the APK.

## Notes for future phone screenshots

Additional Android screenshots can be added under `demo/phone/` using numbered descriptive names. Keep one image per distinct state, avoid repeated captures of the same screen, and update this file with the user-visible behavior demonstrated by each new image.

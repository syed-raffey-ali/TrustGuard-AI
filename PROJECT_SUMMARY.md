# TrustGuard AI — Project Summary

TrustGuard AI is a privacy-first scam interception layer for banks and fintech apps. It protects people at the neglected stage of fraud: the conversation before money moves. A scammer may combine a fake bank call, urgent chat, and OTP request; TrustGuard connects those signals across channels.

The prototype includes a Kotlin/Jetpack Compose Android client, FastAPI realtime gateway, and React mission-control dashboard. It combines deterministic Tier-1 rules, a bundled local classifier, optional Ollama/cloud models, caller context, speech-to-text, and explainable scores with quoted evidence. Users receive safe actions such as verification, hanging up, reporting, blocking, or demo account freezing.

It supports English, Roman Urdu, and Urdu-oriented patterns including bank impersonation, urgency, secrecy, credential harvesting, grooming, and prompt injection. The dashboard exposes live sessions, evidence, model latency, provider health, Paste Analyzer reports, and privacy controls. Analysis remains visible; provider keys stay server-side and raw audio is not persisted.

TrustGuard AI is not a black-box alarm or post-transaction report. It is an auditable, user-triggered early-warning system that helps a person pause before an OTP, PIN, card number, or transfer leaves their control. The repository includes setup automation, demo scenarios, tests, an installable APK, a local model, and web/Android demonstrations.
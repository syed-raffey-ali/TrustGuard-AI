#!/usr/bin/env python3
"""Generate test speech audio (gTTS -> 16 kHz mono PCM16 raw) for call tests."""
import os
import subprocess

from gtts import gTTS

OUT = "/tmp/tg_audio"
os.makedirs(OUT, exist_ok=True)

CLIPS = {
    # English bank-OTP scam (scammer)
    "en_scam": ("en", "Hello, this is ApnaBank fraud department calling. "
                      "We detected a suspicious transaction on your account. "
                      "Your account will be blocked in thirty minutes. "
                      "Please tell me the OTP code I just sent to your number, immediately."),
    # Urdu scam (scammer) — Urdu script, gTTS ur voice
    "ur_scam": ("ur", "السلام علیکم، میں اپنا بینک فراڈ ڈیپارٹمنٹ سے بول رہا ہوں۔ "
                      "آپ کے اکاؤنٹ سے مشکوک لین دین ہوا ہے۔ "
                      "براہ کرم فوری طور پر او ٹی پی کوڈ بتائیں ورنہ اکاؤنٹ بلاک ہو جائے گا۔"),
    # English safe small-talk (control)
    "en_safe": ("en", "Assalam o Alaikum, how are you? Did you eat dinner? "
                      "The weather is really nice today, let's meet for tea tomorrow."),
}

for name, (lang, text) in CLIPS.items():
    mp3 = f"{OUT}/{name}.mp3"
    pcm = f"{OUT}/{name}.pcm"
    gTTS(text=text, lang=lang).save(mp3)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", mp3,
        "-ar", "16000", "-ac", "1", "-f", "s16le", pcm
    ], check=True)
    size = os.path.getsize(pcm)
    print(f"{name}: {size} bytes = {size/32000:.1f}s of 16kHz PCM16")

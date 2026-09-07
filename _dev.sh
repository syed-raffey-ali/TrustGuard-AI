#!/usr/bin/env bash
# TrustGuard physical-device test helpers.
# D1 = 192.168.1.4 (Infinix, @raff)   D2 = 192.168.1.7 (Realme, @moh)
set -e
D1=$(adb devices | grep "^192\.168\.1\.4" | cut -f1)
D2=$(adb devices | grep "^192\.168\.1\.7" | cut -f1)
if [ -z "$D1" ] || [ -z "$D2" ]; then
  adb connect 192.168.1.4 >/dev/null 2>&1 || true
  adb connect 192.168.1.7 >/dev/null 2>&1 || true
  sleep 1
  D1=$(adb devices | grep "^192\.168\.1\.4" | cut -f1)
  D2=$(adb devices | grep "^192\.168\.1\.7" | cut -f1)
fi
echo "D1=$D1 D2=$D2" >&2

shot() {  # shot <device> <name>
  adb -s "$1" exec-out screencap -p > "_shots/$2.png"
  echo "saved _shots/$2.png" >&2
}

tap_text() { # tap_text <device> <text> — uiautomator dump, tap center of node
  local dev="$1" needle="$2"
  adb -s "$dev" shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  local bounds=$(adb -s "$dev" shell cat /sdcard/ui.xml | tr '>' '>\n' | grep -o "text=\"$needle\"[^/]*bounds=\"[^\"]*\"" | grep -o 'bounds="[^"]*"' | head -1 | sed 's/bounds="//;s/"//')
  if [ -z "$bounds" ]; then
    # try content-desc
    bounds=$(adb -s "$dev" shell cat /sdcard/ui.xml | tr '>' '>\n' | grep -o "content-desc=\"$needle\"[^/]*bounds=\"[^\"]*\"" | grep -o 'bounds="[^"]*"' | head -1 | sed 's/bounds="//;s/"//')
  fi
  if [ -z "$bounds" ]; then echo "NOT FOUND: $needle" >&2; return 1; fi
  local x1 y1 x2 y2
  x1=$(echo "$bounds" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1/')
  y1=$(echo "$bounds" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\2/')
  x2=$(echo "$bounds" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\3/')
  y2=$(echo "$bounds" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\4/')
  adb -s "$dev" shell input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 ))
  echo "tapped '$needle' at $(( (x1+x2)/2 )),$(( (y1+y2)/2 ))" >&2
}

type_text() { # type_text <device> <text>
  local dev="$1" txt="$2"
  adb -s "$dev" shell input text "${txt// /%s}"
}

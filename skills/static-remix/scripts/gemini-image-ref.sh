#!/usr/bin/env bash
# gemini-image-ref.sh
#
# Call Nano Banana Pro (gemini-3-pro-image-preview) with a text prompt and
# optionally a reference image attached as base64 inline_data.
#
# Usage:
#   gemini-image-ref.sh \
#     --prompt "..." \
#     --output path/to/out.png \
#     [--aspect-ratio 1:1] \
#     [--reference path/to/product.jpg]
#
# Reads GEMINI_API_KEY from the environment.
#
# Exit codes:
#   0  success — image written to --output
#   1  configuration error (missing key, missing args)
#   2  API or response error — raw response written to <output>.error.json

set -euo pipefail

PROMPT=""
ASPECT="1:1"
OUTPUT=""
REFERENCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt)        PROMPT="$2";    shift 2 ;;
    --aspect-ratio)  ASPECT="$2";    shift 2 ;;
    --output)        OUTPUT="$2";    shift 2 ;;
    --reference)     REFERENCE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROMPT" || -z "$OUTPUT" ]]; then
  echo "usage: --prompt TEXT --output PATH [--aspect-ratio R] [--reference FILE]" >&2
  exit 1
fi
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY not set" >&2
  exit 1
fi
if [[ -n "$REFERENCE" && ! -f "$REFERENCE" ]]; then
  echo "reference file not found: $REFERENCE" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

URL="https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent?key=${GEMINI_API_KEY}"

PAYLOAD=$(PROMPT="$PROMPT" ASPECT="$ASPECT" REFERENCE="$REFERENCE" python3 <<'PY'
import base64, json, mimetypes, os

prompt = os.environ["PROMPT"]
aspect = os.environ["ASPECT"]
ref    = os.environ["REFERENCE"]

parts = [{"text": prompt}]
if ref:
    mime = mimetypes.guess_type(ref)[0] or "image/png"
    with open(ref, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    parts.append({"inline_data": {"mime_type": mime, "data": b64}})

payload = {
    "contents": [{"parts": parts}],
    "generationConfig": {
        "responseModalities": ["IMAGE"],
        "imageConfig": {"aspectRatio": aspect},
    },
}
print(json.dumps(payload))
PY
)

RESPONSE_FILE="$(mktemp)"
HTTP_STATUS=$(curl -sS -o "$RESPONSE_FILE" -w "%{http_code}" \
  -X POST "$URL" \
  -H "Content-Type: application/json" \
  --data-binary @<(printf '%s' "$PAYLOAD"))

if [[ "$HTTP_STATUS" != "200" ]]; then
  cp "$RESPONSE_FILE" "${OUTPUT}.error.json"
  echo "HTTP $HTTP_STATUS — see ${OUTPUT}.error.json" >&2
  rm -f "$RESPONSE_FILE"
  exit 2
fi

OUTPUT="$OUTPUT" RESPONSE_FILE="$RESPONSE_FILE" python3 <<'PY' || exit 2
import base64, json, os, sys

out  = os.environ["OUTPUT"]
with open(os.environ["RESPONSE_FILE"]) as f:
    resp = json.load(f)

try:
    parts = resp["candidates"][0]["content"]["parts"]
except (KeyError, IndexError):
    with open(out + ".error.json", "w") as f:
        json.dump(resp, f, indent=2)
    print(f"no candidates in response — see {out}.error.json", file=sys.stderr)
    raise SystemExit(1)

for p in parts:
    data = p.get("inline_data") or p.get("inlineData")
    if data and "data" in data:
        with open(out, "wb") as f:
            f.write(base64.b64decode(data["data"]))
        print(out)
        raise SystemExit(0)

with open(out + ".error.json", "w") as f:
    json.dump(resp, f, indent=2)
print(f"no inline_data in any part — see {out}.error.json", file=sys.stderr)
raise SystemExit(1)
PY

rm -f "$RESPONSE_FILE"

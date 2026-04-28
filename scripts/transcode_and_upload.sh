#!/bin/bash
# Scale a folder of source videos to 1080p H.264 and (optionally) upload them
# to the kiosk. Run on the Mac; ffmpeg via Homebrew is required.
#
# Usage:
#   transcode_and_upload.sh <source_dir> [staging_dir]
#
# Examples:
#   ./scripts/transcode_and_upload.sh ~/Desktop/ww2_footage
#   ./scripts/transcode_and_upload.sh ~/Movies/raw ~/Movies/kiosk_ready
#
# The script will:
#   1. Find every .mp4/.mov/.mkv/.avi/.m4v in <source_dir>
#   2. Scale each to 1920x? (preserve aspect, even-pixel)
#   3. Re-encode H.264 + AAC into <staging_dir>
#   4. Print an scp command you can run to push them to the kiosk
set -euo pipefail

SRC="${1:-}"
STAGE="${2:-./kiosk_videos_ready}"
SSH_TARGET="ww2-kiosk:/home/orangepi/ww2_kiosk-main/media/videos/"

if [[ -z "$SRC" || ! -d "$SRC" ]]; then
    echo "Usage: $0 <source_dir> [staging_dir]" >&2
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg not found. Install with: brew install ffmpeg" >&2
    exit 1
fi

mkdir -p "$STAGE"

count=0
for f in "$SRC"/*.{mp4,mov,mkv,avi,m4v,MP4,MOV,MKV,AVI,M4V}; do
    [[ -f "$f" ]] || continue
    count=$((count + 1))
    base=$(basename "$f")
    name="${base%.*}"
    out="$STAGE/${name}.mp4"

    if [[ -f "$out" && "$out" -nt "$f" ]]; then
        echo "[$count] Skipping $base (already transcoded, newer than source)"
        continue
    fi

    echo "[$count] Transcoding $base -> $(basename "$out")"
    # Fit each frame inside 1920x1080 preserving aspect, then pad with black
    # bars to exactly 1920x1080. Both upscales 4:3 historical footage AND
    # downscales 4K, so the kiosk never has to scale at runtime.
    ffmpeg -hide_banner -loglevel warning -y -i "$f" \
        -vf "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30" \
        -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p \
        -c:a aac -b:a 128k -movflags +faststart \
        "$out"
done

if (( count == 0 )); then
    echo "No video files found in $SRC" >&2
    exit 1
fi

echo
echo "Transcoded $count file(s) into: $STAGE"
echo
echo "To upload to the kiosk:"
echo "    scp \"$STAGE\"/*.mp4 $SSH_TARGET"
echo
echo "Then visit http://192.168.86.250:8080/buttons to assign them."

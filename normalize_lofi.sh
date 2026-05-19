#!/bin/bash
# ============================================================
# AI-GENERATED FILE
# Created: 2026-04-05
# Purpose: One-time batch script to pre-normalize all LoFi MP3s
#          using ffmpeg loudnorm filter, so the live SoundsBot
#          no longer needs to run loudnorm in real-time.
# ============================================================

LOFI_DIR="/home/leo/live/SoundsBot/sounds/lofi"
NORM_DIR="${LOFI_DIR}_normalized"
BACKUP_DIR="${LOFI_DIR}_original_backup"

mkdir -p "$NORM_DIR"

TOTAL=$(find "$LOFI_DIR" -maxdepth 1 -type f \( -name '*.mp3' -o -name '*.ogg' -o -name '*.wav' -o -name '*.flac' \) | wc -l)
COUNT=0
FAILED=0

echo "=== LoFi Normalization ==="
echo "Source:  $LOFI_DIR"
echo "Output:  $NORM_DIR"
echo "Files:   $TOTAL"
echo ""

for f in "$LOFI_DIR"/*.mp3 "$LOFI_DIR"/*.ogg "$LOFI_DIR"/*.wav "$LOFI_DIR"/*.flac; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f")
    OUTFILE="$NORM_DIR/$BASENAME"

    if [ -f "$OUTFILE" ]; then
        echo "[$((COUNT+1))/$TOTAL] SKIP (exists): $BASENAME"
        COUNT=$((COUNT + 1))
        continue
    fi

    COUNT=$((COUNT + 1))
    echo "[$COUNT/$TOTAL] Normalizing: $BASENAME"

    ffmpeg -y -i "$f" \
        -filter:a "loudnorm=I=-16:TP=-1.5:LRA=11" \
        -ar 48000 -ac 2 \
        -loglevel error \
        "$OUTFILE" 2>&1

    if [ $? -ne 0 ]; then
        echo "  FAILED: $BASENAME"
        FAILED=$((FAILED + 1))
        rm -f "$OUTFILE"
    fi
done

echo ""
echo "=== Done ==="
echo "Processed: $COUNT / $TOTAL"
echo "Failed:    $FAILED"

if [ $FAILED -gt 0 ]; then
    echo "WARNING: $FAILED files failed. Check output above."
    exit 1
fi

NORM_COUNT=$(find "$NORM_DIR" -maxdepth 1 -type f | wc -l)
echo "Normalized files: $NORM_COUNT"

if [ "$NORM_COUNT" -lt "$((TOTAL - 5))" ]; then
    echo "ERROR: Too few normalized files ($NORM_COUNT vs $TOTAL original). Aborting swap."
    exit 1
fi

echo ""
echo "Swapping directories..."
mv "$LOFI_DIR" "$BACKUP_DIR"
mv "$NORM_DIR" "$LOFI_DIR"
echo "Done! Original files backed up to: $BACKUP_DIR"
echo "Normalized files now at: $LOFI_DIR"

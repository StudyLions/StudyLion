# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-22
# Purpose: Pre-encodes ambient sound files to Opus frames at
#          multiple volume levels for efficient looped playback.
# ============================================================

import os
import subprocess
import logging

import discord.opus

logger = logging.getLogger(__name__)

VOLUME_LEVELS = {
    25: 0.25,
    50: 0.50,
    100: 1.0,
}

SOUND_FILES = {
    'rain': 'rain.ogg',
    'campfire': 'campfire.ogg',
    'ocean': 'ocean.ogg',
    'brown_noise': 'brown_noise.ogg',
    'white_noise': 'white_noise.ogg',
}

SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2
FRAME_SAMPLES = 960  # 20ms at 48kHz
PCM_FRAME_BYTES = FRAME_SAMPLES * CHANNELS * SAMPLE_WIDTH  # 3840


class AudioLibrary:
    """Loads all sound files and pre-encodes them to Opus frames at multiple volumes."""

    def __init__(self, sounds_dir: str):
        self._frames: dict[str, dict[int, list[bytes]]] = {}
        self._ensure_opus()
        self._load_all(sounds_dir)

    @staticmethod
    def _ensure_opus():
        if not discord.opus.is_loaded():
            try:
                discord.opus._load_default()
            except Exception:
                for lib in ('libopus.so.0', 'libopus.so', 'libopus.dll', 'opus'):
                    try:
                        discord.opus.load_opus(lib)
                        break
                    except Exception:
                        continue
        if not discord.opus.is_loaded():
            raise RuntimeError("Could not load libopus — required for voice audio")

    def _load_all(self, sounds_dir: str):
        for sound_id, filename in SOUND_FILES.items():
            filepath = os.path.join(sounds_dir, filename)
            if not os.path.isfile(filepath):
                logger.warning("Sound file not found, skipping: %s", filepath)
                continue

            self._frames[sound_id] = {}
            for db_vol, scale in VOLUME_LEVELS.items():
                logger.info("Encoding %s at volume %d%%…", sound_id, db_vol)
                pcm = self._decode(filepath, scale)
                frames = self._encode_opus(pcm)
                self._frames[sound_id][db_vol] = frames
                duration = len(frames) * 0.02
                logger.info("  %s vol=%d%%: %d frames (%.1fs)", sound_id, db_vol, len(frames), duration)

    @staticmethod
    def _decode(filepath: str, volume: float) -> bytes:
        cmd = [
            'ffmpeg', '-i', filepath,
            '-af', f'volume={volume}',
            '-f', 's16le', '-ar', str(SAMPLE_RATE), '-ac', str(CHANNELS),
            '-loglevel', 'quiet', '-',
        ]
        result = subprocess.run(cmd, capture_output=True, check=True)
        return result.stdout

    @staticmethod
    def _encode_opus(pcm_data: bytes) -> list[bytes]:
        encoder = discord.opus.Encoder()
        frames: list[bytes] = []
        for i in range(0, len(pcm_data) - PCM_FRAME_BYTES + 1, PCM_FRAME_BYTES):
            chunk = pcm_data[i : i + PCM_FRAME_BYTES]
            frames.append(encoder.encode(chunk, FRAME_SAMPLES))
        return frames

    def get_source(self, sound_type: str, volume: int = 100) -> 'LoopedOpusSource':
        if sound_type not in self._frames:
            raise ValueError(f"Unknown sound type: {sound_type}")
        available = sorted(VOLUME_LEVELS.keys())
        closest = min(available, key=lambda v: abs(v - volume))
        return LoopedOpusSource(self._frames[sound_type][closest])

    @property
    def available_sounds(self) -> list[str]:
        return list(self._frames.keys())


class LoopedOpusSource(discord.AudioSource):
    """AudioSource that loops pre-encoded Opus frames forever."""

    def __init__(self, frames: list[bytes]):
        self.frames = frames
        self.index = 0

    def read(self) -> bytes:
        if not self.frames:
            return b''
        frame = self.frames[self.index]
        self.index = (self.index + 1) % len(self.frames)
        return frame

    def is_opus(self) -> bool:
        return True

    def cleanup(self) -> None:
        pass

"""p i l k compatibility wrapper - delegates to pysilk."""

from __future__ import annotations

import io
import wave

import pysilk


def _to_bytes(data):
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        with open(data, "rb") as f:
            return f.read()
    if hasattr(data, "read"):
        return data.read()
    raise TypeError("unsupported input type")


def _read_wav_pcm16_mono(wav_data: bytes, expected_rate: int | None = None):
    with wave.open(io.BytesIO(wav_data), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())

    if channels != 1:
        raise ValueError("only mono wav is supported")
    if sampwidth != 2:
        raise ValueError("only 16-bit wav is supported")
    if expected_rate and framerate != expected_rate:
        raise ValueError(f"wav sample rate must be {expected_rate}, got {framerate}")
    return pcm, framerate


def encode(input, output=None, rate=24000, tencent=True):
    wav_bytes = _to_bytes(input)
    pcm, sr = _read_wav_pcm16_mono(wav_bytes, expected_rate=rate)
    silk = pysilk.encode(pcm, data_rate=rate, sample_rate=sr)

    if output is None:
        return silk
    if hasattr(output, "write"):
        output.write(silk)
        return output
    with open(output, "wb") as f:
        f.write(silk)
    return output


def decode(input, output=None, rate=24000, tencent=True):
    silk_bytes = _to_bytes(input)
    pcm = pysilk.decode(silk_bytes, sample_rate=rate)

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    wav_data = wav_buf.getvalue()

    if output is None:
        return wav_data
    if hasattr(output, "write"):
        output.write(wav_data)
        return output
    with open(output, "wb") as f:
        f.write(wav_data)
    return output


def get_duration(path, rate=24000):
    silk_bytes = _to_bytes(path)
    pcm = pysilk.decode(silk_bytes, sample_rate=rate)
    return len(pcm) / 2 / rate

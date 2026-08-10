"""Standalone audio analysis (BPM + key detection) using STFT + autocorrelation.

Extracted from the former DownloadManager so callers do not need a download
context. Windows-friendly: uses soundfile (not librosa.load) to avoid numba
DLL issues.
"""
from typing import Optional

import numpy as np


def _compute_chroma_from_stft(magnitude, frequencies, sr):
    """Compute 12-dimensional chroma features from an STFT magnitude spectrogram."""
    n_frames = magnitude.shape[1]
    chroma = np.zeros((12, n_frames))
    A4_freq = 440.0

    for i, freq in enumerate(frequencies):
        if freq > 0:
            midi_note = 69 + 12 * np.log2(freq / A4_freq)
            pitch_class = int(round(midi_note)) % 12
            chroma[pitch_class, :] += magnitude[i, :]

    for j in range(n_frames):
        col_sum = np.sum(chroma[:, j])
        if col_sum > 0:
            chroma[:, j] /= col_sum

    return chroma


def analyze_audio(audio_path: str) -> dict:
    """Detect BPM and key of an audio file.

    Returns a dict with keys 'bpm', 'key', 'confidence'. On failure every
    value is None.
    """
    try:
        import soundfile as sf
        from scipy import signal

        y, sr = sf.read(audio_path, dtype='float32')
        if len(y.shape) > 1:
            y = np.mean(y, axis=1)

        # Limit to 60 s for speed; enough for a stable tempo/key estimate.
        max_samples = int(sr * 60)
        if len(y) > max_samples:
            y = y[:max_samples]

        hop_length = 512
        n_fft = 2048

        f, t, Zxx = signal.stft(y, fs=sr, nperseg=n_fft, noverlap=n_fft - hop_length)
        magnitude = np.abs(Zxx)

        onset_env = np.sum(np.diff(magnitude, axis=1, prepend=0), axis=0)
        onset_env = np.maximum(0, onset_env)

        autocorr = np.correlate(onset_env, onset_env, mode='full')
        autocorr = autocorr[len(autocorr) // 2:]

        min_lag = int(sr / hop_length * 60 / 200)  # 200 BPM ceiling
        max_lag = int(sr / hop_length * 60 / 60)   # 60 BPM floor

        if max_lag < len(autocorr):
            autocorr_region = autocorr[min_lag:max_lag]
            peak_lag = np.argmax(autocorr_region) + min_lag

            tempo_period = peak_lag * hop_length / sr
            detected_tempo = 60.0 / tempo_period if tempo_period > 0 else 120.0

            candidate_tempos = [detected_tempo]
            if detected_tempo > 140:
                half_tempo = detected_tempo / 2
                if half_tempo >= 60:
                    candidate_tempos.append(half_tempo)
            if detected_tempo < 90:
                double_tempo = detected_tempo * 2
                if double_tempo <= 200:
                    candidate_tempos.append(double_tempo)

            # 80–140 BPM covers most pop/rock/folk — prefer it over octave errors.
            preferred = [x for x in candidate_tempos if 80 <= x <= 140]
            final_tempo = preferred[0] if preferred else detected_tempo
            final_tempo = float(np.clip(final_tempo, 60, 200))
        else:
            final_tempo = 120.0

        chroma = _compute_chroma_from_stft(magnitude, f, sr)
        chroma_mean = np.mean(chroma, axis=1)
        dominant_note_idx = int(np.argmax(chroma_mean))
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        dominant_note = note_names[dominant_note_idx]

        major_intervals = [0, 4, 7]
        minor_intervals = [0, 3, 7]
        major_strength = sum(chroma_mean[(dominant_note_idx + i) % 12] for i in major_intervals)
        minor_strength = sum(chroma_mean[(dominant_note_idx + i) % 12] for i in minor_intervals)

        mode = "major" if major_strength > minor_strength else "minor"
        total = float(np.sum(chroma_mean))
        confidence = float(max(major_strength, minor_strength) / total) if total > 0 else 0.0
        detected_key = f"{dominant_note} {mode}"

        return {
            'bpm': round(final_tempo, 1),
            'key': detected_key,
            'confidence': round(confidence, 2),
        }
    except Exception as e:
        print(f"[audio_analysis] Error analyzing {audio_path}: {e}")
        return {'bpm': None, 'key': None, 'confidence': None}

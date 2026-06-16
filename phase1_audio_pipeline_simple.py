"""
PHASE 1: AUDIO CAPTURE & TRANSCRIPTION PoC (SIMPLIFIED)
========================================================
Same as phase1_audio_pipeline.py, but uses sounddevice instead of PyAudio.
Sounddevice is easier to install on Windows (no C++ compiler needed).

Usage:
  python phase1_audio_pipeline_simple.py

The script will:
  1. List all audio devices (you'll see "CABLE Output")
  2. Listen to VB-Cable for 30 seconds
  3. Transcribe with Whisper API
  4. Print transcribed text

Cost: ~$0.01 per 30 seconds of audio
"""

import sounddevice as sd
import numpy as np
import os
import wave
from dotenv import load_dotenv
from openai import OpenAI
import time

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================================================================
# CONFIGURATION
# ============================================================================

SAMPLE_RATE = 16000  # Whisper API expects 16kHz
CHANNELS = 1  # Mono audio
RECORD_SECONDS = 30  # How long to record (seconds)

# ============================================================================
# STEP 1: FIND VB-CABLE DEVICE
# ============================================================================

def find_vb_cable_device():
    """
    List all audio devices and find VB-Cable.

    Returns:
        device_index (int): Index of VB-Cable device

    Raises:
        RuntimeError: If VB-Cable not found
    """
    print("\n" + "="*70)
    print("AVAILABLE AUDIO DEVICES:")
    print("="*70)

    devices = sd.query_devices()
    vb_cable_index = None

    for i, device in enumerate(devices):
        name = device['name']
        channels = device['max_input_channels']

        # Print all devices
        print(f"  [{i}] {name}")
        print(f"       Input channels: {channels}")

        # Look for VB-Cable
        if 'CABLE' in name.upper() and channels > 0:
            vb_cable_index = i
            print(f"       ✓ Found VB-Cable!")

        print()

    if vb_cable_index is None:
        raise RuntimeError(
            "\n❌ VB-Cable not found!\n"
            "Make sure:\n"
            "  1. VB-Cable is installed (https://vb-audio.com/Cable/)\n"
            "  2. Your computer was restarted after installation\n"
            "  3. VB-Cable is set as default playback device"
        )

    print(f"✓ Using device [{vb_cable_index}] for audio capture")
    return vb_cable_index


# ============================================================================
# STEP 2: CAPTURE AUDIO FROM VB-CABLE
# ============================================================================

def capture_audio(device_index, duration_seconds):
    """
    Capture audio from VB-Cable for specified duration.

    Args:
        device_index (int): sounddevice device index for VB-Cable
        duration_seconds (int): How long to record

    Returns:
        audio_data (numpy.ndarray): Audio samples
    """
    print(f"\n{'='*70}")
    print(f"CAPTURING AUDIO FOR {duration_seconds} SECONDS")
    print(f"{'='*70}")
    print("🎤 Recording... (make sure audio is playing through VB-Cable)")
    print()

    # Calculate total samples needed
    num_samples = int(SAMPLE_RATE * duration_seconds)

    # Record audio
    audio_data = sd.rec(
        frames=num_samples,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        device=device_index,
        dtype=np.int16
    )

    # Show progress while recording
    for i in range(duration_seconds):
        time.sleep(1)
        if (i + 1) % 5 == 0:
            print(f"  {i + 1}s recorded...")

    # Wait for recording to finish
    sd.wait()

    print(f"✓ Recorded {duration_seconds} seconds of audio")
    print(f"  Audio shape: {audio_data.shape}")

    return audio_data


# ============================================================================
# STEP 3: SAVE AUDIO TO WAV FILE (Required by Whisper API)
# ============================================================================

def save_audio_to_file(audio_data, filename="temp_audio.wav"):
    """
    Save audio data to WAV file (Whisper API requires file input).

    Args:
        audio_data (numpy.ndarray): Audio samples from sounddevice
        filename (str): Output filename
    """
    print(f"\n{'='*70}")
    print(f"SAVING AUDIO TO FILE")
    print(f"{'='*70}")

    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio_data.tobytes())

    print(f"✓ Saved to {filename}")
    return filename


# ============================================================================
# STEP 4: TRANSCRIBE WITH WHISPER API
# ============================================================================

def transcribe_with_whisper(audio_file):
    """
    Send audio to Whisper API for transcription.

    Args:
        audio_file (str): Path to audio WAV file

    Returns:
        transcript (str): Transcribed text
    """
    print(f"\n{'='*70}")
    print(f"TRANSCRIBING WITH WHISPER API")
    print(f"{'='*70}")
    print("📡 Sending to OpenAI Whisper API...")

    # Check file size first
    file_size = os.path.getsize(audio_file)
    print(f"   Audio file size: {file_size / 1024:.1f} KB")

    with open(audio_file, 'rb') as f:
        transcript_obj = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="en"
        )

    transcript_text = transcript_obj.text
    print("✓ Transcription complete!")
    print(f"   Transcript length: {len(transcript_text)} characters")

    return transcript_text


# ============================================================================
# STEP 5: MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution: capture → transcribe → print
    """
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  PHASE 1: AUDIO PIPELINE PoC (SIMPLIFIED)".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    try:
        # Step 1: Find VB-Cable
        device_index = find_vb_cable_device()

        # Step 2: Capture audio
        audio_data = capture_audio(device_index, RECORD_SECONDS)

        # Step 3: Save to file
        audio_file = save_audio_to_file(audio_data)

        # Step 4: Transcribe
        transcript = transcribe_with_whisper(audio_file)

        # Step 5: Display results
        print(f"\n{'='*70}")
        print(f"TRANSCRIPTION RESULTS")
        print(f"{'='*70}")
        if transcript.strip():
            print(f"\n{transcript}\n")
        else:
            print(f"\n⚠️  WARNING: Transcript is empty!")
            print("This means Whisper API returned no text.")
            print("Make sure audio was actually playing during recording.\n")

        # Cleanup
        if os.path.exists(audio_file):
            os.remove(audio_file)
            print(f"✓ Cleaned up temp file")

        print("\n" + "█" * 70)
        print("✅ PHASE 1 SUCCESS!")
        print("█" * 70)
        print("\nYour audio was successfully captured and transcribed.")
        print("Next step: Phase 2 - Add KB indexing & validation engine")

    except RuntimeError as e:
        print(f"\n❌ ERROR: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        print("\nTroubleshooting:")
        print("  1. Check .env file has OPENAI_API_KEY=sk-...")
        print("  2. Check VB-Cable is installed and set as default")
        print("  3. Check OpenAI account has billing enabled")
        print(f"\nFull error: {type(e).__name__}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

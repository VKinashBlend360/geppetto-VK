"""
PHASE 1: AUDIO CAPTURE & TRANSCRIPTION PoC
==========================================
Goal: Capture audio from VB-Cable → transcribe with Whisper API → print to console

This is a minimal working example. Captures audio in 10-second chunks,
sends to Whisper API for transcription, and prints results.

Usage:
  python phase1_audio_pipeline.py

The script will:
  1. List all audio devices (you'll see "CABLE Output")
  2. Listen to VB-Cable for 30 seconds
  3. Transcribe with Whisper API
  4. Print transcribed text

Cost: ~$0.01 per 30 seconds of audio (Whisper API)
"""

import pyaudio
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

CHUNK_SIZE = 1024  # Audio chunk size
SAMPLE_RATE = 16000  # Whisper API expects 16kHz
CHANNELS = 1  # Mono audio
FORMAT = pyaudio.paInt16  # 16-bit signed integer
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
    p = pyaudio.PyAudio()

    print("\n" + "="*70)
    print("AVAILABLE AUDIO DEVICES:")
    print("="*70)

    vb_cable_index = None

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        name = info['name']
        channels = info['maxInputChannels']

        # Print all devices
        print(f"  [{i}] {name}")
        print(f"       Input channels: {channels}")

        # Look for VB-Cable
        if 'CABLE' in name.upper() and channels > 0:
            vb_cable_index = i
            print(f"       ✓ Found VB-Cable!")

        print()

    p.terminate()

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
        device_index (int): PyAudio device index for VB-Cable
        duration_seconds (int): How long to record

    Returns:
        audio_data (bytes): Raw audio data
    """
    p = pyaudio.PyAudio()

    print(f"\n{'='*70}")
    print(f"CAPTURING AUDIO FOR {duration_seconds} SECONDS")
    print(f"{'='*70}")
    print("🎤 Recording... (make sure audio is playing through VB-Cable)")
    print()

    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK_SIZE
    )

    frames = []
    num_chunks = int(SAMPLE_RATE / CHUNK_SIZE * duration_seconds)

    # Show progress
    for i in range(num_chunks):
        data = stream.read(CHUNK_SIZE)
        frames.append(data)

        # Progress indicator every 5 seconds
        elapsed = (i * CHUNK_SIZE) / SAMPLE_RATE
        if int(elapsed) % 5 == 0 and i > 0:
            print(f"  {int(elapsed)}s recorded...")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Combine all frames into one audio blob
    audio_data = b''.join(frames)

    print(f"✓ Recorded {duration_seconds} seconds of audio")
    print(f"  Audio size: {len(audio_data) / 1024:.1f} KB")

    return audio_data


# ============================================================================
# STEP 3: SAVE AUDIO TO TEMP FILE (Required by Whisper API)
# ============================================================================

def save_audio_to_file(audio_data, filename="temp_audio.wav"):
    """
    Save raw audio data to WAV file (Whisper API requires file input).

    Args:
        audio_data (bytes): Raw audio data from PyAudio
        filename (str): Output filename
    """
    print(f"\n{'='*70}")
    print(f"SAVING AUDIO TO FILE")
    print(f"{'='*70}")

    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio_data)

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

    with open(audio_file, 'rb') as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="en"
        )

    print("✓ Transcription complete!")
    return transcript.text


# ============================================================================
# STEP 5: MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution: capture → transcribe → print
    """
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  PHASE 1: AUDIO PIPELINE PoC".center(68) + "█")
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
        print(f"\n{transcript}\n")

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
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

"""Isolated acoustic process. No recordings, transcripts or commands.

Run with the verified optional runtime interpreter, never import native KWS
into the listener. Protocol: six-byte startup marker, then a four-byte big
endian PCM length plus mono 16kHz signed-16 audio. Version-two replies are 17
bytes: status (0 no wake, 1 wake, 2 error), first and last phone-start doubles
(-1 absent). The final phone start is not claimed to be the exact word end.
Input is bounded BEFORE reading the payload. The parent imposes a hard deadline.
"""
from pathlib import Path
import struct
import sys

# Direct file execution by the optional venv, without installing app deps.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from luma.keyword_wake import FRAME_BYTES, MAX_FRAMES, KeywordWakeError, load_pinned_candidate


def read_exact(source, length):
    result = bytearray()
    while len(result) < length:
        block = source.read(length - len(result))
        if not block:
            raise EOFError
        result.extend(block)
    return bytes(result)


def serve(verifier, source, output):
    output.write(b'KWS02\n'); output.flush()
    while True:
        try:
            length = struct.unpack('>I', read_exact(source, 4))[0]
            if not 0 < length <= FRAME_BYTES * MAX_FRAMES or length % 2:
                # Cannot safely resynchronize an untrusted oversized frame.
                return
            pcm = read_exact(source, length)
        except EOFError:
            return
        try:
            result = verifier.verify([pcm[offset:offset+FRAME_BYTES]
                                      for offset in range(0, length, FRAME_BYTES)])
            reply = struct.pack('>Bdd', int(result.detected),
                                result.first_token_seconds if result.detected else -1.0,
                                result.last_token_seconds if result.detected else -1.0)
        except Exception:
            # Fixed marker only; no library exception or audio in stderr/stdout.
            reply = struct.pack('>Bdd', 2, -1.0, -1.0)
        output.write(reply); output.flush()


def main():
    if len(sys.argv) != 2:
        raise SystemExit(2)
    try:
        verifier = load_pinned_candidate(Path(sys.argv[1]))
    except KeywordWakeError:
        sys.stdout.buffer.write(b'MODEL\n'); sys.stdout.buffer.flush()
        raise SystemExit(3) from None
    serve(verifier, sys.stdin.buffer, sys.stdout.buffer)


if __name__ == '__main__':
    main()

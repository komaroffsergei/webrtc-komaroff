def _validate_sdp(sdp: str):
    """Basic, strict-ish SDP validation without deep parsing.
    Returns (ok: bool, error: str | None).
    """
    # ASCII only (SDP should be US-ASCII)
    try:
        sdp.encode("ascii")
    except UnicodeEncodeError:
        return False, "SDP must be ASCII"

    # Line structure
    lines = sdp.splitlines()
    if not lines:
        return False, "empty SDP"
    if not lines[0].startswith("v=0"):
        return False, "SDP must start with 'v=0'"
    if len(lines) > 5000:
        return False, "too many SDP lines"
    if any(len(line) > 4096 for line in lines):
        return False, "SDP line too long"

    # Must describe audio media
    if not any(line.startswith("m=audio") for line in lines):
        return False, "no audio media in SDP"

    # ICE credentials usually required for WebRTC offers
    if not any(line.startswith("a=ice-ufrag:") for line in lines):
        return False, "missing a=ice-ufrag"
    if not any(line.startswith("a=ice-pwd:") for line in lines):
        return False, "missing a=ice-pwd"

    return True, None
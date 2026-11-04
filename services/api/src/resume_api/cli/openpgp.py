"""Check one detached OpenPGP signature (v4, RSA, SHA-256 or SHA-512) against a key FoldCV carries, without gpg."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac


class SignatureError(Exception):
    pass


# EMSA-PKCS1-v1_5 DigestInfo prefixes (RFC 8017, section 9.2, note 1), by OpenPGP hash id.
DIGESTS = {8: ("sha256", bytes.fromhex("3031300d060960864801650304020105000420")),
           10: ("sha512", bytes.fromhex("3051300d060960864801650304020305000440"))}
# Subpackets this check reads; a critical one it does not know voids the signature (RFC 4880, 5.2.3.1).
CREATED, ISSUER, ISSUER_FINGERPRINT = 2, 16, 33


@dataclass(frozen=True)
class PublicKey:
    fingerprint: str
    modulus: int
    exponent: int

    @classmethod
    def from_packet(cls, packet: bytes, fingerprint: str) -> "PublicKey":
        """A v4 RSA public-key packet body; its SHA-1 fingerprint must be the one given."""
        found = hashlib.sha1(b"\x99" + len(packet).to_bytes(2, "big") + packet).hexdigest().upper()
        if found != fingerprint or len(packet) < 6 or packet[0] != 4 or packet[5] not in {1, 3}:
            raise SignatureError("unexpected key")
        modulus, offset = _mpi(packet, 6)
        exponent, offset = _mpi(packet, offset)
        if offset != len(packet) or modulus.bit_length() < 2048 or exponent < 3:
            raise SignatureError("unexpected key")
        return cls(fingerprint, modulus, exponent)


def _mpi(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 2 > len(data):
        raise SignatureError("truncated")
    bits = int.from_bytes(data[offset:offset + 2], "big")
    end = offset + 2 + (bits + 7) // 8
    if end > len(data):
        raise SignatureError("truncated")
    return int.from_bytes(data[offset + 2:end], "big"), end


def _crc24(data: bytes) -> int:
    crc = 0xB704CE
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def dearmor(text: bytes) -> bytes:
    """The bytes of one ASCII-armored signature block (RFC 4880, section 6.2), checksum included."""
    try:
        lines = text.decode("ascii").strip().splitlines()
    except UnicodeError:
        raise SignatureError("not armored") from None
    if len(lines) < 4 or lines[0] != "-----BEGIN PGP SIGNATURE-----" or lines[-1] != "-----END PGP SIGNATURE-----":
        raise SignatureError("not armored")
    body = lines[1:-1]
    blank = body.index("") if "" in body else -1
    if blank < 0 or any(":" not in line for line in body[:blank]):
        raise SignatureError("not armored")
    payload = body[blank + 1:]
    checksum = payload.pop() if payload and payload[-1].startswith("=") else None
    try:
        data = base64.b64decode("".join(payload), validate=True)
        if checksum is not None and base64.b64decode(checksum[1:], validate=True) != _crc24(data).to_bytes(3, "big"):
            raise SignatureError("armor checksum")
    except ValueError:
        raise SignatureError("not armored") from None
    return data


def _packet(data: bytes) -> tuple[int, bytes]:
    """The one packet of a binary detached signature: tag and body."""
    if not data or not data[0] & 0x80:
        raise SignatureError("not a packet")
    head = data[0]
    if head & 0x40:
        tag, first = head & 0x3F, data[1] if len(data) > 1 else 0
        if first < 192:
            length, start = first, 2
        elif first < 224:
            length, start = ((first - 192) << 8) + (data[2] if len(data) > 2 else 0) + 192, 3
        elif first == 255:
            length, start = int.from_bytes(data[2:6], "big"), 6
        else:
            raise SignatureError("partial length")
    else:
        tag, kind = (head >> 2) & 0x0F, head & 3
        if kind == 3:
            raise SignatureError("indeterminate length")
        size = 1 << kind
        length, start = int.from_bytes(data[1:1 + size], "big"), 1 + size
    if start + length != len(data):
        raise SignatureError("trailing data")
    return tag, data[start:]


def _subpackets(data: bytes) -> list[tuple[int, bool, bytes]]:
    found, offset = [], 0
    while offset < len(data):
        first = data[offset]
        if first < 192:
            length, offset = first, offset + 1
        elif first < 255:
            if offset + 1 >= len(data):
                raise SignatureError("truncated")
            length, offset = ((first - 192) << 8) + data[offset + 1] + 192, offset + 2
        else:
            length, offset = int.from_bytes(data[offset + 1:offset + 5], "big"), offset + 5
        if length < 1 or offset + length > len(data):
            raise SignatureError("truncated")
        kind = data[offset]
        found.append((kind & 0x7F, bool(kind & 0x80), data[offset + 1:offset + length]))
        offset += length
    return found


def verify(document: bytes, signature: bytes, key: PublicKey) -> None:
    """Raise SignatureError unless `signature` (binary or armored) is the key's binary-document signature of
    `document`."""
    if signature.startswith(b"-----BEGIN PGP SIGNATURE-----"):
        signature = dearmor(signature)
    tag, body = _packet(signature)
    if tag != 2 or len(body) < 6 or body[0] != 4 or body[1] != 0x00 or body[2] not in {1, 3} or body[3] not in DIGESTS:
        raise SignatureError("unexpected signature")
    hashed_length = int.from_bytes(body[4:6], "big")
    hashed_end = 6 + hashed_length
    if hashed_end + 2 > len(body):
        raise SignatureError("truncated")
    unhashed_length = int.from_bytes(body[hashed_end:hashed_end + 2], "big")
    unhashed_end = hashed_end + 2 + unhashed_length
    if unhashed_end + 2 > len(body):
        raise SignatureError("truncated")
    hashed = _subpackets(body[6:hashed_end])
    unhashed = _subpackets(body[hashed_end + 2:unhashed_end])
    if any(critical and kind not in {CREATED, ISSUER, ISSUER_FINGERPRINT} for kind, critical, _ in hashed + unhashed):
        raise SignatureError("unknown critical subpacket")
    if not any(kind == CREATED and len(value) == 4 for kind, _, value in hashed):
        raise SignatureError("no creation time")
    issuers = [value[1:].hex().upper() for kind, _, value in hashed if kind == ISSUER_FINGERPRINT and len(value) == 21]
    if any(issuer != key.fingerprint for issuer in issuers):
        raise SignatureError("another key")
    name, prefix = DIGESTS[body[3]]
    trailer = body[:hashed_end] + b"\x04\xff" + hashed_end.to_bytes(4, "big")
    digest = hashlib.new(name, document + trailer).digest()
    if body[unhashed_end:unhashed_end + 2] != digest[:2]:
        raise SignatureError("digest mismatch")
    value, end = _mpi(body, unhashed_end + 2)
    if end != len(body) or not 0 < value < key.modulus:
        raise SignatureError("unexpected signature")
    size = (key.modulus.bit_length() + 7) // 8
    expected = b"\x00\x01" + b"\xff" * (size - 3 - len(prefix) - len(digest)) + b"\x00" + prefix + digest
    if not hmac.compare_digest(pow(value, key.exponent, key.modulus).to_bytes(size, "big"), expected):
        raise SignatureError("bad signature")


def key(packet_base64: str, fingerprint: str) -> PublicKey:
    return PublicKey.from_packet(base64.b64decode(packet_base64, validate=True), fingerprint)

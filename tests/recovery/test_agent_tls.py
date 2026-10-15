"""Pinned HTTPS keeps both chain and hostname verification with a bundled CA set."""

from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/api/src"))
from resume_api.agent.web import PinnedConnection


def test_pinned_https_rejects_untrusted_and_wrong_name_but_accepts_a_trusted_named_peer(tmp_path, monkeypatch):
    certificate, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    config = tmp_path / "openssl.cnf"
    config.write_text("[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=v3\n[dn]\nCN=public.example\n[v3]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\nsubjectAltName=DNS:public.example\n")
    subprocess.run(["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-config", str(config), "-keyout", str(key), "-out", str(certificate)],
        check=True, capture_output=True, timeout=5)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(certificate, key)
    class ConnectedSocket(socket.socket):
        def connect(self, address):
            assert address == ("93.184.215.14", 443)
    def connect(host):
        client, peer = socket.socketpair()
        stream = ConnectedSocket(family=socket.AF_UNIX, type=socket.SOCK_STREAM, fileno=client.detach())
        stream.settimeout(2); peer.settimeout(2)
        def serve():
            try:
                with context.wrap_socket(peer, server_side=True) as secured: secured.sendall(b"x")
            except ssl.SSLError:
                peer.close()
        worker = threading.Thread(target=serve); worker.start()
        connection = PinnedConnection(host, 443, "93.184.215.14", True, 2)
        try:
            with monkeypatch.context() as patch:
                patch.setattr("resume_api.agent.web.socket.socket", lambda *args, **kwargs: stream)
                connection.connect()
            assert connection.sock.recv(1) == b"x"
        finally:
            connection.close(); worker.join(3)
            assert not worker.is_alive()
    with pytest.raises(ssl.SSLCertVerificationError): connect("public.example")
    monkeypatch.setattr("resume_api.agent.web.certifi.where", lambda: str(certificate))
    with pytest.raises(ssl.SSLCertVerificationError, match="Hostname mismatch"): connect("wrong.example")
    connect("public.example")

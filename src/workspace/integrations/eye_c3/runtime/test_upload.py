import hashlib
from contextlib import closing
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote
import zlib

from upload_server import Store, make_server

SAMPLE = b"\x00\x00\x00\x18ftypisom" + bytes(range(251)) * 2000


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(self.folder.name, "test-key", "/not-used-in-software-tests")
        self.store.decode = lambda item: None
        self.server = make_server("127.0.0.1", 0, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.folder.cleanup()

    def request(self, payload=SAMPLE, headers_only=False, **changes):
        headers = {"X-Media-Key": "test-key", "X-File-Name": quote("测试视频.mp4"),
                   "X-File-CRC32": "%08x" % (zlib.crc32(payload) & 0xffffffff)}
        headers.update(changes)
        with closing(http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)) as client:
            if headers_only:
                client.putrequest("POST", "/upload")
                client.putheader("Content-Length", str(len(payload)))
                for name, value in headers.items():
                    client.putheader(name, value)
                client.endheaders()
            else:
                client.request("POST", "/upload", payload, headers)
            response = client.getresponse()
            return response.status, json.loads(response.read())

    def test_exact_bytes_crc_hash_and_metadata(self):
        status, item = self.request()
        self.assertEqual(status, 201)
        self.assertEqual(item["sha256"], hashlib.sha256(SAMPLE).hexdigest())
        self.assertEqual((Path(self.folder.name) / (item["id"] + ".mp4")).read_bytes(), SAMPLE)
        self.assertEqual(self.store.items()[0]["name"], "测试视频.mp4")
        self.assertFalse(item["hdmi_verified"])

    def test_wrong_key(self):
        self.assertEqual(self.request(headers_only=True, **{"X-Media-Key": "wrong"})[0], 403)
        self.assertEqual(self.store.items(), [])

    def test_cross_origin(self):
        self.assertEqual(self.request(headers_only=True, **{"Origin": "http://example.com"})[0], 403)

    def test_path_traversal_name(self):
        self.assertEqual(self.request(headers_only=True, **{"X-File-Name": quote("../other.mp4")})[0], 400)

    def test_bad_magic(self):
        self.assertEqual(self.request(payload=b"not a video at all")[0], 415)
        self.assertEqual(self.store.items(), [])

    def test_wrong_crc_not_published(self):
        self.assertEqual(self.request(**{"X-File-CRC32": "00000000"})[0], 422)
        self.assertEqual(self.store.items(), [])
        self.assertEqual(len(list(Path(self.folder.name).glob("*.mp4.part"))), 1)

    def test_storage_quota_does_not_delete(self):
        with patch.object(self.store, "available", return_value=False):
            self.assertEqual(self.request(headers_only=True)[0], 507)

    def test_simultaneous_upload_refused(self):
        self.store.upload_lock.acquire()
        try:
            self.assertEqual(self.request(headers_only=True)[0], 409)
        finally:
            self.store.upload_lock.release()

    def test_interrupted_upload_not_published(self):
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as sock:
            headers = ("POST /upload HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n"
                       "X-Media-Key: test-key\r\nX-File-Name: a.mp4\r\n"
                       "X-File-CRC32: 00000000\r\nContent-Length: 100000\r\n\r\n") % self.port
            sock.sendall(headers.encode() + SAMPLE[:128])
            sock.shutdown(socket.SHUT_WR)
            sock.recv(1024)
        self.assertEqual(self.store.items(), [])

    def test_duplicate_filename_does_not_overwrite(self):
        first = self.request()[1]
        second = self.request()[1]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.items()), 2)


if __name__ == "__main__":
    unittest.main()

import hashlib
import struct
import unittest

from open_omada_device_agent.crypto import calculate_md5_mode_auth
from open_omada_device_agent.ecsp import MessageType, build_message, decode_frame, encode_frame


class EcspCodecTests(unittest.TestCase):
    def test_length_prefixed_json_round_trip(self):
        msg = build_message(
            mac="02:11:22:33:44:55",
            msg_type=MessageType.DISCOVERY,
            body={"deviceInfo": {"isFactory": True}},
            version="2.3.0",
            ver_cap=2,
        )
        frame = encode_frame(msg)
        declared = struct.unpack("!I", frame[:4])[0]
        self.assertEqual(declared, len(frame) - 4)
        self.assertEqual(decode_frame(frame), msg)

    def test_message_types(self):
        self.assertEqual(int(MessageType.DISCOVERY), 1)
        self.assertEqual(int(MessageType.EVENT_PORTAL_QUERY), 64)
        self.assertEqual(int(MessageType.EVENT_PORTAL_AUTH), 128)
        self.assertEqual(int(MessageType.EVENT_PORTAL_AUTH_RESPONSE), 352)
        self.assertEqual(int(MessageType.INFORM_REQUEST), 256)
        self.assertEqual(int(MessageType.GET_REQUEST), 24576)
        self.assertEqual(int(MessageType.GET_RESPONSE), 28672)
        self.assertEqual(int(MessageType.PRE_CONNECT_INFO_RESPONSE), 0x100000)
        self.assertEqual(int(MessageType.DEVICE_VERIFY_INFO), 0x100001)
        self.assertEqual(int(MessageType.SYSTEM_VERIFY_RESULT), 0x100003)
        self.assertEqual(int(MessageType.REPORT), 0x150000)

    def test_legacy_auth_matches_java_algorithm_shape(self):
        user = "lab"
        password = "test-password"
        key = "12345678-1234-1234-1234-123456789abc"
        md5pwd = hashlib.md5(password.encode()).hexdigest().upper()
        first = hashlib.sha256((user + md5pwd).encode()).hexdigest().upper()
        expected = hashlib.sha256((first + key).encode()).hexdigest().upper()
        self.assertEqual(calculate_md5_mode_auth(user, password, key), expected)


if __name__ == "__main__":
    unittest.main()

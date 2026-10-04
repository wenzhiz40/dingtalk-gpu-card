import io
import json
import unittest
from unittest.mock import patch

from dingtalk_api import DingTalkClient


class _Response:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class DingTalkClientTest(unittest.TestCase):
    @patch("dingtalk_api.urllib.request.urlopen")
    def test_create_targets_one_group_and_disables_forwarding(self, urlopen):
        urlopen.side_effect = [
            _Response({"accessToken": "TOKEN", "expireIn": 7200}),
            _Response({}),
        ]
        client = DingTalkClient("CLIENT", "SECRET")
        track_id = client.create_and_deliver_card(
            "TEMPLATE.schema", "GROUP_ID", {"summary": "ok"}
        )
        self.assertTrue(track_id)
        request = urlopen.call_args_list[1].args[0]
        body = json.loads(request.data)
        self.assertEqual("dtv1.card//IM_GROUP.GROUP_ID", body["openSpaceId"])
        self.assertEqual({"robotCode": "CLIENT"}, body["imGroupOpenDeliverModel"])
        self.assertFalse(body["imGroupOpenSpaceModel"]["supportForward"])
        self.assertNotIn("SECRET", request.data.decode())
        self.assertEqual("TOKEN", request.headers["X-acs-dingtalk-access-token"])

    @patch("dingtalk_api.urllib.request.urlopen")
    def test_send_group_text(self, urlopen):
        urlopen.side_effect = [
            _Response({"accessToken": "TOKEN", "expireIn": 7200}),
            _Response({"processQueryKey": "QUERY"}),
        ]
        client = DingTalkClient("CLIENT", "SECRET")
        self.assertEqual("QUERY", client.send_group_text("GROUP_ID", "GPU 0 可使用"))
        request = urlopen.call_args_list[1].args[0]
        body = json.loads(request.data)
        self.assertEqual("sampleText", body["msgKey"])
        self.assertEqual("GROUP_ID", body["openConversationId"])
        self.assertEqual({"content": "GPU 0 可使用"}, json.loads(body["msgParam"]))


if __name__ == "__main__":
    unittest.main()

"""Minimal DingTalk OpenAPI client using only Python's standard library."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid


API_ROOT = "https://api.dingtalk.com"


class DingTalkError(RuntimeError):
    pass


class DingTalkClient:
    def __init__(self, client_id: str, client_secret: str, timeout: int = 15):
        self.client_id = client_id
        self._client_secret = client_secret
        self.timeout = timeout
        self._token = ""
        self._token_expires_at = 0.0

    def _request(
        self, method: str, path: str, body: dict, *, authenticated: bool = True
    ) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if authenticated:
            headers["x-acs-dingtalk-access-token"] = self.access_token()
        request = urllib.request.Request(
            API_ROOT + path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")[:1000]
            raise DingTalkError(
                f"钉钉接口返回 HTTP {exc.code}: {response_text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise DingTalkError(f"无法连接钉钉接口: {exc.reason}") from exc

    def access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        result = self._request(
            "POST",
            "/v1.0/oauth2/accessToken",
            {"appKey": self.client_id, "appSecret": self._client_secret},
            authenticated=False,
        )
        token = result.get("accessToken", "")
        if not token:
            raise DingTalkError("钉钉没有返回 accessToken，请检查 Client ID/Secret")
        expires_in = int(result.get("expireIn", 7200))
        self._token = token
        self._token_expires_at = time.time() + max(60, expires_in - 300)
        return token

    def create_and_deliver_card(
        self,
        template_id: str,
        open_conversation_id: str,
        card_data: dict[str, str],
    ) -> str:
        out_track_id = str(uuid.uuid4())
        self._request(
            "POST",
            "/v1.0/card/instances/createAndDeliver",
            {
                "cardTemplateId": template_id,
                "outTrackId": out_track_id,
                "cardData": {"cardParamMap": card_data},
                "callbackType": "STREAM",
                "openSpaceId": f"dtv1.card//IM_GROUP.{open_conversation_id}",
                "imGroupOpenSpaceModel": {"supportForward": False},
                "imGroupOpenDeliverModel": {"robotCode": self.client_id},
            },
        )
        return out_track_id

    def update_card(self, out_track_id: str, card_data: dict[str, str]) -> None:
        self._request(
            "PUT",
            "/v1.0/card/instances",
            {
                "outTrackId": out_track_id,
                "cardData": {"cardParamMap": card_data},
            },
        )

    def send_group_text(self, open_conversation_id: str, content: str) -> str:
        """Send a proactive plain-text message as the installed enterprise bot."""
        result = self._request(
            "POST",
            "/v1.0/robot/groupMessages/send",
            {
                "robotCode": self.client_id,
                "openConversationId": open_conversation_id,
                "msgKey": "sampleText",
                "msgParam": json.dumps({"content": content}, ensure_ascii=False),
            },
        )
        return str(result.get("processQueryKey", ""))

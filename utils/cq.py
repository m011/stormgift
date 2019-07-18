import aiohttp
from config import CQBOT
from cqhttp import CQHttp


class CQClient:
    def __init__(self, api_root, access_token=None, timeout=5):
        self.api_root = api_root.strip().rstrip("/") + "/"
        self.timeout = timeout
        self.headers = {
            "User-Authorization": f"Bearer {access_token or ''}",
        }

    def __getattr__(self, item):
        url = self.api_root + item

        async def parse(**data):
            try:
                status, resp_json = await self.request(url, data)
            except Exception as e:
                return False, f"Error: {e}"
            return True, resp_json

        return parse

    async def request(self, url, data):
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        client_session = aiohttp.ClientSession(timeout=timeout)
        async with client_session as session:
            async with session.post(url, json=data, headers=self.headers) as resp:
                status_code = resp.status
                resp_json = await resp.json()
                return status_code, resp_json


bot = CQHttp(**CQBOT)
qq = CQClient(api_root=CQBOT["api_root"], access_token=CQBOT["access_token"])
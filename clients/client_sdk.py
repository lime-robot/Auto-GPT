import asyncio
import websockets
import requests
import os

AUTO_ASKUP_API_KEY = os.environ["AUTO_ASKUP_API_KEY"]

class AutoAskUpClient:
    def __init__(self, base_url, api_key=AUTO_ASKUP_API_KEY, base_path="autoaskup", secure=False):
        self.base_url = base_url
        self.base_path = base_path
        self.session = requests.Session()
        self.protocol = "https" if secure else "http"
        self.ws_protocol = "wss" if secure else "ws"
        self.apikey = api_key

    def init_task(self, prompt):
        payload = {"prompt": prompt}
        url = f"{self.protocol}://{self.base_url}/{self.base_path}"
        headers = {"Authorization": self.apikey}
        response = self.session.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            response_data = response.json()
            print(response_data)
            return response_data.get("task_id")
        return None

    async def connect(self, task_id):
        uri = f"{self.ws_protocol}://{self.base_url}/{self.base_path}/ws/{task_id}"
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                print(message)
                if message == "TERMINATE":
                    return


if __name__ == "__main__":
    # Usage:
    client = AutoAskUpClient("localhost:8000")
    task_id = client.init_task(prompt="Find top ai companies like Upstage.ai")
    if task_id:
        asyncio.run(client.connect(task_id))

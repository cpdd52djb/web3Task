import asyncio, sys, loguru, time
import random
import string

from curl_cffi.requests import AsyncSession
from eth_account.messages import encode_defunct
from web3 import AsyncWeb3

logger = loguru.logger
logger.remove()
logger.add(sys.stdout, colorize=True, format="<g>{time:HH:mm:ss:SSS}</g> | <level>{message}</level>")


class Twitter:
    def __init__(self, auth_token):
        self.auth_token = auth_token
        bearer_token = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
        defaulf_headers = {
            "authority": "twitter.com",
            "origin": "https://twitter.com",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "authorization": bearer_token,
        }
        defaulf_cookies = {"auth_token": auth_token}
        self.Twitter = AsyncSession(headers=defaulf_headers, cookies=defaulf_cookies, timeout=120, impersonate="chrome120")
        self.auth_code = None

    async def get_auth_code(self, client_id, state, code_challenge):
        try:
            params = {
                'code_challenge': code_challenge,
                'code_challenge_method': 'plain',
                'client_id': client_id,
                'redirect_uri': 'https://info-api.macaron.xyz/twitter/callback',
                'response_type': 'code',
                'scope': 'users.read tweet.read follows.write',
                'state': state
            }
            response = await self.Twitter.get('https://x.com/i/api/2/oauth2/authorize', params=params)
            if "code" in response.json() and response.json()["code"] == 353:
                self.Twitter.headers.update({"x-csrf-token": response.cookies["ct0"]})
                return await self.get_auth_code(client_id, state, code_challenge)
            elif response.status_code == 429:
                await asyncio.sleep(5)
                return self.get_auth_code(client_id, state, code_challenge)
            elif 'auth_code' in response.json():
                self.auth_code = response.json()['auth_code']
                return True
            logger.error(f'{self.auth_token} 获取auth_code失败')
            return False
        except Exception as e:
            logger.error(e)
            return False

    async def twitter_authorize(self, client_id, state, code_challenge):
        try:
            if not await self.get_auth_code(client_id, state, code_challenge):
                return False
            data = {
                'approval': 'true',
                'code': self.auth_code,
            }
            response = await self.Twitter.post('https://x.com/i/api/2/oauth2/authorize', data=data)
            if 'redirect_uri' in response.text:
                return True
            elif response.status_code == 429:
                await asyncio.sleep(5)
                return self.twitter_authorize(client_id, state, code_challenge)
            logger.error(f'{self.auth_token}  推特授权失败')
            return False
        except Exception as e:
            logger.error(f'{self.auth_token}  推特授权异常：{e}')
            return False


class Macaron:
    def __init__(self, private_key: str, auth_token: str, nstChannelID: str, nstPassword: str):
        session = ''.join(random.choice(string.digits + string.ascii_letters) for _ in range(10))
        nstproxy = f"http://{nstChannelID}-residential-country_ANY-r_5m-s_{session}:{nstPassword}@gw-us.nstproxy.com:24125"
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider('https://arbitrum.blockpi.network/v1/rpc/public'))
        self.client = AsyncSession(proxy=nstproxy, timeout=120, impersonate="chrome120")
        self.account = self.w3.eth.account.from_key(private_key)
        self.twitter = Twitter(auth_token)

    async def login(self):
        try:
            deadline = int(time.time() + 600)
            sig_msg = f'[Macaron] Please sign to let us verify that you are the owner of this address {self.account.address.lower()}.[{deadline}]'
            signature = self.account.sign_message(encode_defunct(text=sig_msg)).signature.hex()
            json_data = {
                "account": self.account.address,
                "signature": signature,
                "deadline": deadline
            }
            res = await self.client.post("https://api.macaron.xyz/auth/login", json=json_data)
            if res.status_code == 201 and 'jwt_token' in res.text:
                jwt_token = res.json()['jwt_token']
                self.client.headers.update({"Authorization": f"Bearer {jwt_token}"})
                logger.success(f"[{self.account.address}] 登录成功")
                return await self.task()
            if res.status_code == 404:
                return await self.getAuthUrl()
            logger.error(f"[{self.account.address}] 登录失败")
            return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 登录失败：{e}")
            return False

    async def getAuthUrl(self):
        try:
            msg_info = 'Enjoy Macaron, earn Macaron points'
            signature = self.account.sign_message(encode_defunct(text=msg_info))
            params = {
                'wallet_address': self.account.address,
                'signature': signature['signature'].hex(),
            }
            res = await self.client.get("https://info-api.macaron.xyz/twitter/auth_url", params=params)
            print(res.json())
            if res.status_code == 200 and res.json()['statusCode'] == 200:
                auth_url = res.json()['data']['auth_url'] + "&"
                state = auth_url.split("state=")[1].split("&")[0]
                code_challenge = auth_url.split("code_challenge=")[1].split("&")[0]
                client_id = auth_url.split("client_id=")[1].split("&")[0]
                return await self.bindTwitter(client_id, state, code_challenge)
            logger.error(f"[{self.account.address}] 登录失败")
            return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 登录失败：{e}")
            return False

    async def bindTwitter(self, client_id, state, code_challenge):
        try:
            if not await self.twitter.twitter_authorize(client_id, state, code_challenge):
                return False
            params = {
                'state': state,
                'code': self.twitter.auth_code,
            }
            res = await self.client.get("https://info-api.macaron.xyz/twitter/callback", params=params, allow_redirects=False)
            if res.status_code == 302:
                Location = res.headers['Location']
                if Location == 'https://twitter.com/macarondex':
                    return await self.verify()
            logger.error(f"[{self.account.address}] 绑定推特失败")
            return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 绑定推特失败：{e}")
            return False

    async def verify(self):
        try:
            res = await self.client.get(f"https://info-api.macaron.xyz/twitter/verify?wallet_address={self.account.address}&type=follow")
            if res.status_code == 200 and res.json()['statusCode'] == 200:
                jwt_token = res.json()['data']['jwt_token']
                self.client.headers.update({"Authorization": f"Bearer {jwt_token}"})
                logger.success(f"[{self.account.address}] 绑定推特成功")
                return await self.task()
            elif res.json()['statusCode'] == 401:
                await asyncio.sleep(5)
                return await self.verify()
            logger.error(f"[{self.account.address}] 获取信息失败")
            return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 获取信息失败：{e}")
            return False

    async def task(self):
        try:
            res = await self.client.get(f"https://api.macaron.xyz/points/user/task")
            if res.status_code == 200:
                taskIds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
                if len(res.json()) > 0:
                    for task in res.json():
                        task_id = task['task_id']
                        taskIds.remove(task_id)
                        if task['completed_status'] == 'false':
                            await self.completed(task['task_id'])
                        elif task['claimed_status'] == 'false':
                            await self.claim(task['task_id'])
                if len(taskIds) == 0:
                    logger.success(f"[{self.account.address}] 任务已全部完成")
                    return True
                for taskID in taskIds:
                    await self.completed(taskID)
                return await self.task()
        except Exception as e:
            logger.error(f"[{self.account.address}] 任务失败：{e}")

    async def completed(self, taskID):
        try:
            json_data = {"task_id": taskID}
            res = await self.client.post(f"https://api.macaron.xyz/points/task/completed", json=json_data)
            if res.status_code == 201 and res.json()['completed_status'] == "true":
                if res.json()['claimed_status'] == "false":
                    return await self.claim(taskID)
                else:
                    logger.success(f"[{self.account.address}] 任务{taskID}已完成")
                    return True
            logger.error(f"[{self.account.address}] 任务{taskID}未完成")
            return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 任务{taskID}未完成：{e}")
            return False

    async def claim(self, taskID):
        try:
            json_data = {"task_id": taskID}
            res = await self.client.post(f"https://api.macaron.xyz/points/task/claimed", json=json_data)
            if res.status_code == 201 and res.json()['claimed_status'] == "true":
                logger.success(f"[{self.account.address}] 任务{taskID}领取成功")
                return True
            logger.error(f"[{self.account.address}] 任务{taskID}领取失败")
            return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 任务{taskID}领取失败：{e}")
            return False


async def do(semaphore, private_key, auth_token, nstChannelID, nstPassword):
    async with semaphore:
        for _ in range(3):
            if await Macaron(private_key, auth_token, nstChannelID, nstPassword).login():
                break


async def main(filePath, nstChannelID, nstPassword):
    semaphore = asyncio.Semaphore(10)
    task = []
    with open(filePath, 'r') as f:
        for account_line in f:
            account_line = account_line.strip().split('----')
            task.append(do(semaphore, account_line[1].strip(), account_line[2].strip(), nstChannelID, nstPassword))

    await asyncio.gather(*task)


if __name__ == '__main__':
    _filePath = input("请输入账户文件路径：").strip()
    _nstChannelID = input("请输入nstproxy通道ID：").strip()
    _nstPassword = input("请输入nstproxy通道密码：").strip()
    asyncio.run(main(_filePath, _nstChannelID, _nstPassword))

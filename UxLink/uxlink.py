import asyncio, sys
import hashlib
import random
import string
from datetime import datetime
from httpx import AsyncClient
from eth_account.messages import encode_defunct
from web3 import AsyncWeb3
from loguru import logger

logger.remove()
logger.add(sys.stdout, colorize=True, format="<g>{time:HH:mm:ss:SSS}</g> | <level>{message}</level>")


class UXLink:
    def __init__(self, private_key: str, nstChannelID: str, nstPassword: str):
        RPC_list = [
            'https://arbitrum.llamarpc.com', 'https://arb1.arbitrum.io/rpc', 'https://rpc.ankr.com/arbitrum',
            'https://1rpc.io/arb', 'https://arb-pokt.nodies.app', 'https://arbitrum.blockpi.network/v1/rpc/public',
            'https://arbitrum-one.public.blastapi.io', 'https://arb-mainnet-public.unifra.io',
            'https://arbitrum-one-rpc.publicnode.com', 'https://arbitrum.meowrpc.com', 'https://arbitrum.drpc.org'
        ]
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(random.choice(RPC_list)))
        session = ''.join(random.choice(string.digits + string.ascii_letters) for _ in range(10))
        nstproxy = f"http://{nstChannelID}-residential-country_ANY-r_5m-s_{session}:{nstPassword}@gw-us.nstproxy.com:24125"
        proxies = {'all://': nstproxy}
        self.client = AsyncClient(proxies=proxies, timeout=120)
        self.account = self.w3.eth.account.from_key(private_key)
        self.Mint_add = self.w3.to_checksum_address('0x5d6297441ce0b6e68ba979c7144c31b5b80ad49b')
        abi = [{
            "inputs": [
                {"internalType": "uint256", "name": "date", "type": "uint256"},
                {"internalType": "uint256", "name": "amount", "type": "uint256"},
                {"internalType": "bytes", "name": "signature", "type": "bytes"},
                {"internalType": "string", "name": "transId", "type": "string"}
            ],
            "name": "checkIn",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }]
        self.Mint = self.w3.eth.contract(address=self.Mint_add, abi=abi)

    async def getNonce(self):
        try:
            json_data = {"eventName": "dappLoginPage", "eventType": "loginInfo",
                         "eventValue": "{\"isInBinance\":false,\"userInfo\":{\"address\":\"\",\"userName\":\"\",\"userAvatar\":\"\",\"userGender\":0,\"userUid\":\"\",\"did\":\"\",\"location\":\"\",\"userBio\":\"\",\"defaultAddress\":\"\",\"bindEmail\":true,\"userStatus\":0,\"defaultWalletType\":0,\"needBindTg\":false,\"needBindX\":false,\"isBindTg\":false,\"isBindX\":false}}"
                         }
            res = await self.client.post(f"https://api.uxlink.io/uxtag/event", json=json_data)
            if res.json()['success']:
                return res.json()['data']['eventResp']
            else:
                return None
        except Exception as e:
            logger.error(f"获取Nonce失败：{e}")
            return None

    async def login(self):
        try:
            nonce = await self.getNonce()
            if nonce is None:
                logger.error(f"[{self.account.address}] 获取Nonce失败")
                return False
            sig_msg = f'Welcome to UXLINK!\n\nClick to sign in and this request will not trigger a blockchain transaction or cost any gas fees.\n\nWallet address:\n{self.account.address}\n\nNonce:\n{hashlib.md5(nonce.encode()).hexdigest()}'
            signature = self.account.sign_message(encode_defunct(text=sig_msg))
            json_data = {
                "address": self.account.address.lower(),
                "aliasName": "Binance",
                "walletType": 5,
                "inviteCode": "",
                "message": sig_msg,
                "signed": signature['signature'].hex()
            }
            res = await self.client.post("https://api.uxlink.io/user/wallet/verify", json=json_data)
            if res.json()['success']:
                logger.success(f"[{self.account.address}] 登录成功")
                accessToken = res.json()['data']['accessToken']
                self.client.headers.update({"Authorization": f"{accessToken}"})
                return await self.wallet()
            else:
                logger.error(f"[{self.account.address}] 登录失败")
                return False
        except Exception as e:
            logger.error(f"[{self.account.address}] 登录失败：{e}")
            return False

    async def wallet(self):
        try:
            json_data = {
                "activityId": "1782964205154988035",
                "walletAddress": self.account.address.lower()
            }
            res = await self.client.post("https://api.uxlink.io/activity/uxcheckin/third/wallet", json=json_data)
            if res.json()['success']:
                amount = res.json()['data']['amount']
                amount = int(amount)
                dateToken = res.json()['data']['dateToken']
                dateToken = int(dateToken)
                transId = res.json()['data']['transId']
                signature = res.json()['data']['signature']
                signature = f"0x{signature.lower()}"
                logger.success(f"[{self.account.address}] 获取Mint信息成功")
                tx = await self.Mint.functions.checkIn(dateToken, amount, signature, transId).build_transaction({
                    'from': self.account.address,
                    'chainId': 42161,
                    'nonce': await self.w3.eth.get_transaction_count(self.account.address),
                    'gas': 262262,
                    'maxFeePerGas': self.w3.to_wei(0.02, 'gwei'),
                    'maxPriorityFeePerGas': 10,
                })
                tx['gas'] = await self.w3.eth.estimate_gas(tx)
                signed_tx = self.account.sign_transaction(tx)
                tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                logger.info(f"[{self.account.address}] Mint交易hash: {tx_hash.hex()}")
                return True
            elif res.json()['code'] == 6001015:
                logger.error(f"[{self.account.address}] 今日已签到")
                return True
            else:
                logger.error(f"[{self.account.address}] 获取Mint信息失败")
                return False
        except Exception as e:
            if 'Already Checked In!' in str(e):
                logger.error(f"[{self.account.address}] 已经签到过了")
                return True
            logger.error(f"[{self.account.address}] 获取Mint信息失败：{e}")
            return False


async def do(semaphore, private_key, nstChannelID, nstPassword):
    async with semaphore:
        for _ in range(3):
            if await UXLink(private_key, nstChannelID, nstPassword).login():
                break


async def main(filePath, nstChannelID, nstPassword):
    semaphore = asyncio.Semaphore(10)
    with open(filePath, 'r') as f:
        task = [do(semaphore, account_line.strip().split('----')[1].strip(), nstChannelID, nstPassword) for account_line in f]
    hour = 13
    while True:
        if hour == 13:
            await asyncio.gather(*task)
        else:
            logger.info(f"{13}点运行，当前时间{hour}点，等待中...")
        await asyncio.sleep(3000)
        hour = datetime.now().hour


if __name__ == '__main__':
    print('账户文件格式：地址----私钥')
    _filePath = input("请输入账户文件路径：").strip()
    _nstChannelID = input("请输入nstproxy通道ID：").strip()
    _nstPassword = input("请输入nstproxy通道密码：").strip()
    asyncio.run(main(_filePath, _nstChannelID, _nstPassword))

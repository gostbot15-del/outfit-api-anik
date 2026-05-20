from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import requests
import time
import logging
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import protobuf files
import my_pb2
import output_pb2
import GetOutfit_pb2

# Static config only (no updater)
STATIC_CONFIG = {
    "IND": {
        "client_url": "client.ind.freefiremobile.com",
        "server_url": "https://loginbp.ggpolarbear.com",
        "release_version": "OB53",
        "client_version": "1.123.10"
    },
    "AMERICA": {
        "client_url": "client.us.freefiremobile.com",
        "server_url": "https://loginbp.ggpolarbear.com",
        "release_version": "OB53",
        "client_version": "1.123.10"
    },
    "OTHERS": {
        "client_url": "clientbp.ggpolarbear.com",
        "server_url": "https://loginbp.ggpolarbear.com",
        "release_version": "OB53",
        "client_version": "1.123.10"
    }
}

def get_version_config(region):
    if region == "IND":
        return STATIC_CONFIG["IND"]
    elif region in ["BR", "US", "NA", "SAC"]:
        return STATIC_CONFIG["AMERICA"]
    else:
        return STATIC_CONFIG["OTHERS"]

app = Flask(__name__)

# Simple cache for Vercel
class SimpleCache:
    def __init__(self):
        self.cache = {}
    
    def get(self, key):
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value, timeout=25200):
        self.cache[key] = (value, time.time() + timeout)

cache = SimpleCache()

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV  = b'6oyZDr22E3ychjM%'

def encrypt_message(plaintext: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(plaintext, AES.block_size))

REGION_CRED = {
    "IND":    {"uid": "4816833368", "password": "Account_GPEQSBVFD_BY_SOLANKI_DADY"},
    "AMERICA": {"uid": "4765721099", "password": "C60B035E09E4F41DDE31921CD4338BEF751A14532B3FFEC044056BB6C1F33763"},
    "OTHERS": {"uid": "4828310793", "password": "02B6697C482937FFCE91B1A2021CE89FB06DADC2F0B26806769B891ACD3A5B6C"}
}

def get_cred(region):
    if region == "IND":
        return REGION_CRED["IND"]
    elif region in ["BR","US","NA","SAC"]:
        return REGION_CRED["AMERICA"]
    return REGION_CRED["OTHERS"]

def get_jwt_token(region):
    cache_key = f"jwt_{region}"
    tok = cache.get(cache_key)
    if tok:
        return tok

    cred = get_cred(region)
    cfg = get_version_config(region)

    try:
        oauth_resp = requests.post(
            "https://100067.connect.garena.com/oauth/guest/token/grant",
            data={
                'uid': cred['uid'],
                'password': cred['password'],
                'response_type': "token",
                'client_type': "2",
                'client_secret': "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
                'client_id': "100067"
            },
            headers={'User-Agent': 'GarenaMSDK/4.0.19P9'},
            timeout=8
        )
        if oauth_resp.status_code != 200:
            return None
        oauth_data = oauth_resp.json()
        access_token = oauth_data.get('access_token')
        open_id = oauth_data.get('open_id')
        if not access_token or not open_id:
            return None
    except Exception as e:
        return None

    game_data = my_pb2.GameData()
    game_data.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    game_data.game_name = "free fire"
    game_data.game_version = 1
    game_data.version_code = cfg["client_version"]
    game_data.open_id = open_id
    game_data.access_token = access_token
    game_data.platform_type = 4
    game_data.field_99 = "4"
    game_data.field_100 = "4"

    serialized = game_data.SerializeToString()
    encrypted_req = encrypt_message(serialized)

    major_url = f"{cfg['server_url'].rstrip('/')}/MajorLogin"
    headers = {
        "User-Agent": "Dalvik/2.1.0",
        "Content-Type": "application/octet-stream",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": cfg["release_version"]
    }
    try:
        resp = requests.post(major_url, data=encrypted_req, headers=headers, timeout=8)
        if resp.status_code == 200:
            msg = output_pb2.Garena_420()
            msg.ParseFromString(resp.content)
            if msg.token:
                cache.set(cache_key, msg.token, timeout=25200)
                return msg.token
    except Exception as e:
        pass
    return None

def fetch_outfit(jwt_token, account_id, region):
    req = GetOutfit_pb2.CSGetOutfitReq()
    req.AccountId = account_id
    plaintext = req.SerializeToString()
    encrypted_body = encrypt_message(plaintext)

    cfg = get_version_config(region)
    base_url = cfg["client_url"].rstrip('/')
    url = f"https://{base_url}/GetAccountOutfit"

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": base_url,
        "ReleaseVersion": cfg["release_version"],
        "User-Agent": "Free Fire MAX/2019117050 CFNetwork/3860.200.71 Darwin/25.1.0",
        "X-GA": "v1 1",
        "X-Unity-Version": "2022.3.47f1"
    }
    try:
        resp = requests.post(url, data=encrypted_body, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}

        res = GetOutfit_pb2.CSGetOutfitRes()
        res.ParseFromString(resp.content)

        return {
            "WeaponSkinShows": list(res.WeaponSkinShows),
            "ProfileInfo": {
                "CharacterId": res.ProfileInfo.CharacterId,
                "SkinColor": res.ProfileInfo.SkinColor,
                "Clothes": list(res.ProfileInfo.Clothes),
                "Skills": [
                    {
                        "SkillId": s.SkillId
                    }
                    for s in res.ProfileInfo.EquippedSkills
                ]
            }
        }
    except Exception as e:
        return {"error": str(e)}

@app.route('/outfit', methods=['GET'])
def outfit():
    uid = request.args.get('uid')
    region = request.args.get('region')
    
    if not uid:
        return jsonify({"error": "Missing uid parameter"}), 400
    
    if not region:
        region = "BD"
    
    region = region.upper()
    
    if region == "BD":
        actual_region = "OTHERS"
    else:
        actual_region = region
    
    jwt_token = get_jwt_token(actual_region)
    if not jwt_token:
        return jsonify({"error": "JWT generation failed"}), 500
    
    try:
        result = fetch_outfit(jwt_token, int(uid), actual_region)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    result["credit"] = "t.me/danger_ff_dev"
    result["requested_region"] = region
    result["actual_region"] = actual_region
    
    return jsonify(result)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Free Fire Outfit API is running!",
        "endpoint": "/outfit?uid=USER_ID&region=REGION",
        "regions": ["BD (default)", "IND", "BR", "US", "NA", "SAC"],
        "example": "/outfit?uid=123456789"
    })

# For Vercel serverless
app.debug = False

# This is the handler Vercel expects
handler = app

# For local testing
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1080)

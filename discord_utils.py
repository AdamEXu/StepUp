from flask import redirect, request, session
import requests
import os

CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI')
API_BASE_URL = "https://discord.com/api"
AUTHORIZATION_BASE_URL = API_BASE_URL + "/oauth2/authorize"
USER_URL = API_BASE_URL + "/users/@me"
TOKEN_URL = API_BASE_URL + "/oauth2/token"

def get_discord_login_url():
    return f"{AUTHORIZATION_BASE_URL}?response_type=code&client_id={CLIENT_ID}&scope=identify+email&redirect_uri={REDIRECT_URI}&prompt=consent"

def get_token(code):
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': 'identify',
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.post(TOKEN_URL, data=data, headers=headers)
    return response.json()

def get_user_info(token):
    headers = {
        'Authorization': f"Bearer {token}"
    }
    response = requests.get(USER_URL, headers=headers)
    return response.json()
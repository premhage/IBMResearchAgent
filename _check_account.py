import requests, os
from dotenv import load_dotenv
load_dotenv("research_agent/.env")

API_KEY = os.environ["WATSONX_API_KEY"]

# Get IAM token + decode the account info from it
r = requests.post("https://iam.cloud.ibm.com/identity/token",
    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": API_KEY},
    headers={"Content-Type": "application/x-www-form-urlencoded"})
data = r.json()
token = data["access_token"]

# Introspect the token to find the account
intr = requests.post("https://iam.cloud.ibm.com/identity/introspect",
    data={"token": token},
    headers={"Content-Type": "application/x-www-form-urlencoded",
             "Authorization": f"Basic Yng6Yng="})  # public bx:bx basic auth
print("Token introspection status:", intr.status_code)
if intr.status_code == 200:
    info = intr.json()
    print(f"  sub (user):    {info.get('sub','?')}")
    print(f"  email:         {info.get('email', info.get('username','?'))}")
    account = info.get('account', {})
    print(f"  account id:    {account.get('bss','?')}")
    print(f"  account valid: {account.get('valid','?')}")
    iam = info.get('iam_id','?')
    print(f"  iam_id:        {iam}")

# Try listing API keys to see which account this belongs to
keys_r = requests.get("https://iam.cloud.ibm.com/v1/apikeys?account_id=self&pagesize=3",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
print(f"\nAPI keys list status: {keys_r.status_code}")
if keys_r.status_code == 200:
    keys = keys_r.json().get("apikeys", [])
    print(f"  Found {len(keys)} key(s) in this account")
    for k in keys[:3]:
        print(f"    name={k.get('name','?')}  created={k.get('created_at','?')[:10]}")

# Check projects via dataplatform with explicit content-type
print("\n--- dataplatform.cloud.ibm.com project list ---")
p2 = requests.get("https://api.dataplatform.cloud.ibm.com/v2/projects?limit=10",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
print(f"  status: {p2.status_code}")
if p2.status_code == 200:
    items = p2.json().get("resources", [])
    print(f"  total_results: {p2.json().get('total_results', 0)}")
    for p in items:
        guid  = p.get("metadata", {}).get("guid","?")
        pname = p.get("entity",   {}).get("name","?")
        print(f"    -> {guid} | {pname}")

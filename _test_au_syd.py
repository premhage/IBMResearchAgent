import requests, os
from dotenv import load_dotenv
load_dotenv("research_agent/.env")

API_KEY    = os.environ["WATSONX_API_KEY"]
PROJECT_ID = "3c059543-877b-400e-8cb5-3847ebb295ff"

# IAM token
r = requests.post("https://iam.cloud.ibm.com/identity/token",
    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": API_KEY},
    headers={"Content-Type": "application/x-www-form-urlencoded"})
token = r.json()["access_token"]
print("IAM: OK")
hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Try the exact URL from the browser screenshot
# Browser shows: au-syd.dai.cloud.ibm.com/projects/3c059543.../manage/general
base_dai = "https://api.dataplatform.cloud.ibm.com"
base_au  = "https://au-syd.dai.cloud.ibm.com"
base_ml  = "https://au-syd.ml.cloud.ibm.com"

print("\n--- Trying dataplatform API paths ---")
paths = [
    f"{base_dai}/v2/projects/{PROJECT_ID}",
    f"{base_au}/v2/projects/{PROJECT_ID}",
    f"{base_dai}/v2/projects?limit=5",
    f"{base_au}/v2/projects?limit=5",
]
for url in paths:
    try:
        resp = requests.get(url, headers=hdrs, timeout=10)
        print(f"  {url.replace('https://','')[:60]}")
        print(f"    -> {resp.status_code}")
        if resp.status_code == 200:
            print(f"    -> BODY: {str(resp.json())[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n--- Check WML instance association for project ---")
wml_url = f"{base_ml}/v4/spaces?project_id={PROJECT_ID}"
resp2 = requests.get(wml_url, headers=hdrs, timeout=10)
print(f"  WML spaces: {resp2.status_code}")

print("\n--- Generate test with project_id in header (alt method) ---")
gen_url = f"{base_ml}/ml/v1/text/generation?version=2023-05-29"
payload = {
    "model_id": "ibm/granite-3-8b-instruct",
    "project_id": PROJECT_ID,
    "input": "Hello, respond with just: CONNECTED",
    "parameters": {"max_new_tokens": 10}
}
resp3 = requests.post(gen_url, headers=hdrs, json=payload, timeout=20)
print(f"  Generation status: {resp3.status_code}")
if resp3.status_code == 200:
    results = resp3.json().get("results", [])
    if results:
        print(f"  GRANITE RESPONSE: {results[0].get('generated_text','')}")
        print("  *** CONNECTION SUCCESSFUL ***")
else:
    print(f"  Error body: {resp3.text[:400]}")

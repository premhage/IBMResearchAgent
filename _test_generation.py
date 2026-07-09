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
print(f"IAM: OK  (account = {r.json().get('token_type','?')})")
hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# ── 1. Try the cpd-managed key (auto-created by Watson Studio)
# The screenshot shows "cpd-apikey-IBMid-6A2000G8NX-2026-07-08T12:07:49Z"
# That key is auto-managed by Studio — let's try the ML REST API with THIS key
# We'll test a direct generation call to see which project IDs are accepted

# ── 2. Try ALL dataplatform endpoints for the project
print("\n--- au-syd dataplatform endpoints ---")
bases = [
    "https://au-syd.ml.cloud.ibm.com",
    "https://api.dataplatform.cloud.ibm.com",
    "https://au-syd.dai.cloud.ibm.com",
]
for base in bases:
    # Try project lookup
    url = f"{base}/v2/projects/{PROJECT_ID}"
    try:
        resp = requests.get(url, headers=hdrs, timeout=8)
        print(f"  {base}/v2/projects/{{id}} -> {resp.status_code}")
        if resp.status_code == 200:
            name = resp.json().get("entity", {}).get("name", "?")
            print(f"    *** FOUND: {name} ***")
    except Exception as e:
        print(f"  {base}: ERROR {e}")

# ── 3. Try a direct Granite generation with project_id (au-syd)
print("\n--- Direct Granite generation test (au-syd) ---")
for model in ["ibm/granite-8b-code-instruct", "ibm/granite-guardian-3-8b"]:
    url = "https://au-syd.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
    payload = {
        "model_id": model,
        "project_id": PROJECT_ID,
        "input": "Say: CONNECTED",
        "parameters": {"max_new_tokens": 8}
    }
    resp = requests.post(url, headers=hdrs, json=payload, timeout=20)
    print(f"  {model}: HTTP {resp.status_code}")
    if resp.status_code == 200:
        txt = resp.json().get("results", [{}])[0].get("generated_text", "")
        print(f"    Response: {txt.strip()}")
        print(f"    *** MODEL WORKS WITH THIS PROJECT ***")
    else:
        msg = resp.json().get("errors", [{}])[0].get("message", resp.text[:120]) if resp.headers.get("content-type","").startswith("application/json") else resp.text[:120]
        print(f"    Error: {msg}")

# ── 4. Try us-south (more Granite models)
print("\n--- Direct Granite generation test (us-south) ---")
url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
payload = {
    "model_id": "ibm/granite-3-8b-instruct",
    "project_id": PROJECT_ID,
    "input": "Say: CONNECTED",
    "parameters": {"max_new_tokens": 8}
}
resp = requests.post(url, headers=hdrs, json=payload, timeout=20)
print(f"  granite-3-8b-instruct (us-south): HTTP {resp.status_code}")
if resp.status_code == 200:
    txt = resp.json().get("results", [{}])[0].get("generated_text", "")
    print(f"    Response: {txt.strip()}  *** WORKS ***")
else:
    try:
        msg = resp.json().get("errors", [{}])[0].get("message", "")
    except:
        msg = resp.text[:150]
    print(f"    Error: {msg}")

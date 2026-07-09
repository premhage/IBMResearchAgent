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

# Try every known IBM Cloud regional ML / DAI endpoint
candidates = [
    ("au-syd ML",   "https://au-syd.ml.cloud.ibm.com"),
    ("au-syd DAI",  "https://au-syd.dai.cloud.ibm.com"),
    ("us-south ML", "https://us-south.ml.cloud.ibm.com"),
    ("eu-de ML",    "https://eu-de.ml.cloud.ibm.com"),
    ("eu-gb ML",    "https://eu-gb.ml.cloud.ibm.com"),
    ("jp-tok ML",   "https://jp-tok.ml.cloud.ibm.com"),
    ("ca-tor ML",   "https://ca-tor.ml.cloud.ibm.com"),
]

hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("\n--- Direct project lookup ---")
for label, base in candidates:
    try:
        url = f"{base}/v2/projects/{PROJECT_ID}"
        resp = requests.get(url, headers=hdrs, timeout=8)
        status = resp.status_code
        if status == 200:
            name = resp.json().get("entity", {}).get("name", "?")
            print(f"  [{label}] FOUND  -> Name: {name}  URL: {base}")
        else:
            print(f"  [{label}] {status}")
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")

print("\n--- List projects (v2) ---")
for label, base in candidates:
    try:
        url = f"{base}/v2/projects?limit=5"
        resp = requests.get(url, headers=hdrs, timeout=8)
        if resp.status_code == 200:
            items = resp.json().get("resources", [])
            if items:
                print(f"  [{label}] {len(items)} project(s):")
                for p in items:
                    guid  = p.get("metadata", {}).get("guid", "?")
                    pname = p.get("entity",   {}).get("name", "?")
                    print(f"    ID={guid}  Name={pname}")
            else:
                print(f"  [{label}] 200 but no projects")
        else:
            print(f"  [{label}] {resp.status_code}")
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")

print("\n--- Granite model availability ---")
for label, base in candidates[:4]:
    try:
        url = f"{base}/ml/v1/foundation_model_specs?version=2024-09-16&filters=function_text_generation"
        resp = requests.get(url, headers=hdrs, timeout=8)
        if resp.status_code == 200:
            ids = [m["model_id"] for m in resp.json().get("resources", []) if "granite" in m.get("model_id","")]
            print(f"  [{label}] Granite models: {ids[:5]}")
        else:
            print(f"  [{label}] models: {resp.status_code}")
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")

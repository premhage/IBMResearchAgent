import requests, os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.environ["WATSONX_API_KEY"]
PROJECT_ID = os.environ["WATSONX_PROJECT_ID"]
WX_URL = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

# ── Step 1: Get IAM token ──────────────────────────────────────────────────
r = requests.post("https://iam.cloud.ibm.com/identity/token",
    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": API_KEY},
    headers={"Content-Type": "application/x-www-form-urlencoded"})
assert r.status_code == 200, f"IAM failed: {r.text}"
token = r.json()["access_token"]
print(f"[OK] IAM token acquired (len={len(token)})")

# ── Step 2: List all projects ─────────────────────────────────────────────
pr = requests.get(f"{WX_URL}/v2/projects?limit=20",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
print(f"[INFO] /v2/projects status: {pr.status_code}")
if pr.status_code == 200:
    projects = pr.json().get("resources", [])
    if not projects:
        print("[WARN] No projects visible to this API key.")
    else:
        print(f"[OK] Found {len(projects)} project(s):")
        for p in projects:
            meta = p.get("metadata", {})
            ent  = p.get("entity", {})
            print(f"       ID: {meta.get('guid','?')}   Name: {ent.get('name','?')}")
else:
    print(f"[ERR] {pr.text[:400]}")

# ── Step 3: Try direct project lookup ────────────────────────────────────
direct = requests.get(f"{WX_URL}/v2/projects/{PROJECT_ID}",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
print(f"[INFO] Direct project ({PROJECT_ID}) status: {direct.status_code}")
if direct.status_code == 200:
    name = direct.json().get("entity", {}).get("name", "?")
    print(f"[OK] Project accessible! Name: {name}")
else:
    print(f"[ERR] {direct.text[:300]}")

# ── Step 4: List available Granite models ────────────────────────────────
models_r = requests.get(
    f"{WX_URL}/ml/v1/foundation_model_specs?version=2024-09-16&filters=function_text_generation",
    headers={"Authorization": f"Bearer {token}"})
print(f"[INFO] Models status: {models_r.status_code}")
if models_r.status_code == 200:
    models = [m["model_id"] for m in models_r.json().get("resources", []) if "granite" in m["model_id"]]
    print(f"[OK] Granite models available: {models[:8]}")
else:
    print(f"[ERR] Models: {models_r.text[:200]}")

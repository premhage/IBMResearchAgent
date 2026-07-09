import requests, os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.environ["WATSONX_API_KEY"]

# Get IAM token
r = requests.post("https://iam.cloud.ibm.com/identity/token",
    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": API_KEY},
    headers={"Content-Type": "application/x-www-form-urlencoded"})
token = r.json()["access_token"]
print("IAM: OK")

regions = [
    ("au-syd",   "https://au-syd.ml.cloud.ibm.com"),
    ("us-south", "https://us-south.ml.cloud.ibm.com"),
    ("eu-gb",    "https://eu-gb.ml.cloud.ibm.com"),
    ("eu-de",    "https://eu-de.ml.cloud.ibm.com"),
    ("jp-tok",   "https://jp-tok.ml.cloud.ibm.com"),
]
found_any = False
for name, url in regions:
    resp = requests.get(f"{url}/v2/projects?limit=10",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=8)
    if resp.status_code == 200:
        projects = resp.json().get("resources", [])
        if projects:
            found_any = True
            print(f"\n[{name}] {len(projects)} project(s) found:")
            for p in projects:
                guid = p.get("metadata", {}).get("guid", "?")
                pname = p.get("entity", {}).get("name", "?")
                print(f"   ID   : {guid}")
                print(f"   Name : {pname}")
                print(f"   URL  : {url}")
                print()
        else:
            print(f"[{name}] no projects")
    else:
        print(f"[{name}] HTTP {resp.status_code}")

if not found_any:
    print("\nNo projects found in any region for this API key.")
    print("You need to create a watsonx.ai project at:")
    print("  https://dataplatform.cloud.ibm.com/projects/")

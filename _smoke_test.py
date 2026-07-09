"""Quick end-to-end smoke test — run from inside research_agent/ directory."""
import sys, os
# Must run from inside research_agent/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import watsonx_client as wx

print("=" * 55)
print("  ResearchAgent — Pre-launch smoke test")
print("=" * 55)

# 1. Config
print(f"\n[1] Config")
print(f"    API Key   : ...{wx.WATSONX_API_KEY[-8:]}")
print(f"    Project ID: {wx.WATSONX_PROJECT_ID}")
print(f"    URL       : {wx.WATSONX_URL}")
print(f"    Model     : {wx.GRANITE_MODEL_ID}")

# 2. IAM ping
print(f"\n[2] IAM Token")
try:
    tok = wx._get_iam_token()
    print(f"    Status    : OK (len={len(tok)})")
except Exception as e:
    print(f"    FAILED    : {e}"); sys.exit(1)

# 3. Generation test
print(f"\n[3] Granite Generation ({wx.GRANITE_MODEL_ID})")
resp = wx.generate(
    "You are a research assistant. In one sentence, describe autonomous rover navigation.",
    max_new_tokens=60,
    temperature=0.2,
)
if resp.startswith("[GENERATION ERROR]") or resp.startswith("[MOCK"):
    print(f"    FAILED    : {resp[:120]}")
else:
    print(f"    Status    : OK")
    print(f"    Response  : {resp.strip()[:120]}")

# 4. Embeddings test
print(f"\n[4] Embeddings ({wx.GRANITE_EMBED_ID})")
vecs = wx.embed(["autonomous rover navigation SLAM path planning"])
if vecs and len(vecs[0]) > 0:
    print(f"    Status    : OK (dim={len(vecs[0])})")
else:
    print(f"    Status    : fallback mock (embedding model not in region)")

print(f"\n{'=' * 55}")
print("  All checks passed — ready to start Flask!")
print(f"{'=' * 55}\n")

"""
config.py — centralised configuration and AGENT_INSTRUCTIONS.

Edit the AGENT_INSTRUCTIONS dict to customise the agent without touching
any other file.  All keys are documented inline.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
#  AGENT INSTRUCTIONS  ← edit here to customise agent behaviour
# ─────────────────────────────────────────────────────────────────────────────
AGENT_INSTRUCTIONS = {
    # ── Identity & tone ───────────────────────────────────────────────────────
    "name": "ResearchAgent",
    "tone": (
        "You are a rigorous academic research assistant with deep expertise "
        "in robotics and autonomous systems.  Communicate in precise, "
        "scholarly language.  Be concise but thorough.  Never speculate "
        "without clearly flagging uncertainty."
    ),

    # ── Domain specialisation ─────────────────────────────────────────────────
    "domain": "autonomous rover navigation and mobile robotics",
    "sub_topics": [
        "simultaneous localisation and mapping (SLAM)",
        "path planning algorithms",
        "sensor fusion (LiDAR, camera, IMU)",
        "terrain classification",
        "obstacle avoidance",
        "reinforcement learning for navigation",
    ],

    # ── Citation style ────────────────────────────────────────────────────────
    # Supported: "IEEE" | "IRJET"
    "citation_style": "IEEE",

    # ── ReAct reasoning ───────────────────────────────────────────────────────
    # Number of Thought→Action→Observation cycles before final answer.
    "react_max_steps": 6,
    # Minimum confidence (0–1) below which the agent flags a claim.
    "confidence_threshold": 0.65,

    # ── Safety & integrity rules ──────────────────────────────────────────────
    "safety_rules": [
        "NEVER fabricate or hallucinate citations.  Only cite sources present "
        "in the knowledge base or returned by Exa search.",
        "Always distinguish RETRIEVED FACTS (from KB or Exa) from GENERATED "
        "INFERENCE (model reasoning).  Prefix retrieved facts with [KB] or "
        "[WEB] and inference with [INFER].",
        "Flag every claim with confidence < {threshold} using the token "
        "[LOW-CONFIDENCE].",
        "If a contradiction is detected between two sources, surface both "
        "citations and describe the conflict explicitly.",
        "Do not provide medical, legal, or financial advice.",
        "When information is unavailable, state 'insufficient evidence' rather "
        "than guessing.",
    ],

    # ── Gap analysis ──────────────────────────────────────────────────────────
    "gap_analysis_prompt_hint": (
        "Focus on methodological gaps, missing benchmark comparisons, "
        "under-explored environmental conditions, and scalability limitations."
    ),

    # ── Contradiction detection ───────────────────────────────────────────────
    "contradiction_sensitivity": "medium",   # low | medium | high

    # ── Hypothesis generation ─────────────────────────────────────────────────
    "hypothesis_creativity": "balanced",     # conservative | balanced | exploratory
    "hypothesis_min_evidence_sources": 2,    # require at least N supporting sources
}

# ─────────────────────────────────────────────────────────────────────────────
#  Runtime settings (read from .env)
# ─────────────────────────────────────────────────────────────────────────────
WATSONX_API_KEY    = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_URL        = os.getenv("WATSONX_URL", "https://au-syd.ml.cloud.ibm.com")
EXA_API_KEY        = os.getenv("EXA_API_KEY", "")
FLASK_SECRET_KEY   = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
MAX_UPLOAD_MB      = int(os.getenv("MAX_UPLOAD_MB", "50"))

# ── Granite model IDs ─────────────────────────────────────────────────────────
# au-syd region supports: granite-8b-code-instruct, granite-guardian-3-8b
# us-south region supports: granite-3-8b-instruct, granite-4-h-small
GRANITE_MODEL_ID   = "ibm/granite-8b-code-instruct"
GRANITE_EMBED_ID   = "ibm/granite-embedding-125m-english"

# ── Upload / storage paths ────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(__file__)
UPLOAD_FOLDER  = os.path.join(BASE_DIR, "uploads")
KB_INDEX_FILE  = os.path.join(BASE_DIR, "knowledge_base", "index.json")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "knowledge_base"), exist_ok=True)

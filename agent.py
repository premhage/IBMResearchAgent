"""
agent.py — ReAct-style Research Agent.

Implements the Thought → Action → Observation loop with tools:
  • search_kb       – semantic search over local PDF knowledge base
  • exa_search      – live Exa neural web search
  • gap_analysis    – identify unexplored directions across all papers
  • contradiction   – detect conflicting claims between sources
  • hypothesis      – generate hypotheses with evidence scoring
  • cite            – format references in IEEE / IRJET style

The agent also exposes standalone analysis methods used by the dashboard.
"""
from __future__ import annotations

import json
import re
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import watsonx_client as wx
import exa_client as exa
from knowledge_base import kb
from config import AGENT_INSTRUCTIONS


# ─────────────────────────────────────────────────────────────────────────────
#  Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReActStep:
    step_type: str      # "thought" | "action" | "observation" | "answer"
    content: str
    tool: Optional[str] = None
    tool_args: Optional[dict] = None
    source: str = "INFER"  # "INFER" | "KB" | "WEB"
    confidence: float = 1.0


@dataclass
class AgentResponse:
    query: str
    steps: list[ReActStep] = field(default_factory=list)
    final_answer: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  Citation formatter
# ─────────────────────────────────────────────────────────────────────────────

def _format_citation(paper: dict[str, Any], index: int, style: str) -> dict[str, Any]:
    title   = paper.get("title", "Untitled")
    authors = paper.get("authors", "Unknown")
    year    = paper.get("year", "n.d.")
    url     = paper.get("url", "")

    if style.upper() == "IRJET":
        formatted = f'[{index}] {authors}, "{title}," IRJET, vol. X, no. X, {year}.'
    else:  # IEEE default
        formatted = f'[{index}] {authors}, "{title}," {year}.'
        if url:
            formatted += f" [Online]. Available: {url}"

    return {
        "index": index,
        "title": title,
        "authors": authors,
        "year": year,
        "formatted": formatted,
        "url": url,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt builders
# ─────────────────────────────────────────────────────────────────────────────

def _safety_block() -> str:
    threshold = AGENT_INSTRUCTIONS["confidence_threshold"]
    rules = AGENT_INSTRUCTIONS["safety_rules"]
    rules_text = "\n".join(
        f"- {r.replace('{threshold}', str(threshold))}"
        for r in rules
    )
    return f"SAFETY RULES (mandatory):\n{rules_text}"


def _system_prompt() -> str:
    ai = AGENT_INSTRUCTIONS
    domain = ai["domain"]
    sub_topics = ", ".join(ai["sub_topics"])
    threshold  = ai["confidence_threshold"]
    return textwrap.dedent(f"""
        You are a rigorous academic research assistant specialising in {domain}.
        Sub-topics: {sub_topics}.
        Citation style: {ai['citation_style']}.

        MANDATORY RULES:
        - NEVER fabricate citations. Only cite sources present in the context below.
        - Prefix facts from the knowledge base with [KB]. Prefix live web facts with [WEB]. Prefix your own reasoning with [INFER].
        - Flag claims you are less than {int(threshold*100)}% confident about with [LOW-CONFIDENCE].
        - If information is insufficient, say so explicitly.

        You will reason step by step, then give a complete answer.
        Use this format EXACTLY:

        Thought: <what you observe about the context and what the user needs>
        Action: search_kb — reviewing the provided knowledge base chunks
        Observation: <summarise what the KB chunks tell you>
        Thought: <what additional insight you can add>
        Action: synthesise — combining KB evidence with reasoning
        Observation: <key points assembled>
        Final Answer: <complete, well-cited scholarly response using [KB], [WEB], [INFER] tags>
    """).strip()


def _react_prompt(query: str, context_chunks: list[dict], web_results: list[dict]) -> str:
    kb_block = ""
    if context_chunks:
        kb_block = "=== LOCAL KNOWLEDGE BASE ===\n" + "\n---\n".join(
            f"[KB:{i+1}] Source: '{c['title']}' ({c['year']})\n{c['chunk']}"
            for i, c in enumerate(context_chunks)
        )
    else:
        kb_block = "=== LOCAL KNOWLEDGE BASE ===\n(No papers uploaded yet.)"

    web_block = ""
    if web_results:
        web_block = "\n=== LIVE WEB RESULTS (Exa) ===\n" + "\n---\n".join(
            f"[WEB:{i+1}] {r['title']} ({r.get('published_date','')[:7]})\n{r['text_snippet']}"
            for i, r in enumerate(web_results)
        )

    return (
        f"{_system_prompt()}\n\n"
        f"{kb_block}\n{web_block}\n\n"
        f"=== USER QUESTION ===\n{query}\n\n"
        f"Now reason step by step and answer:\n\n"
        f"Thought:"
    )


def _gap_analysis_prompt(corpus_summary: str) -> str:
    hint = AGENT_INSTRUCTIONS.get("gap_analysis_prompt_hint", "")
    return textwrap.dedent(f"""
        {_system_prompt()}

        You are performing a systematic gap analysis across the following research corpus.
        Hint: {hint}

        CORPUS:
        {corpus_summary[:6000]}

        Identify 5–8 specific, actionable research gaps.  For each gap provide:
        - gap_title: short title
        - description: 2–3 sentence explanation
        - missing_evidence: what kind of study/experiment is absent
        - potential_impact: why filling this gap matters
        - confidence: your confidence (0–1) that this is a genuine gap

        Output ONLY a valid JSON array with keys: gap_title, description,
        missing_evidence, potential_impact, confidence.
        Do not wrap in markdown code fences.
    """).strip()


def _contradiction_prompt(corpus_summary: str) -> str:
    return textwrap.dedent(f"""
        {_system_prompt()}

        Detect contradictions and conflicting claims in the following research corpus.

        CORPUS:
        {corpus_summary[:6000]}

        For each contradiction found, output JSON with keys:
          claim_a, source_a, claim_b, source_b, conflict_type,
          severity (low/medium/high), explanation.

        Severity guide:
          high   = directly opposing quantitative results
          medium = differing methodological conclusions
          low    = different emphasis / scope

        Output ONLY a valid JSON array.  Do not wrap in markdown code fences.
        If no contradictions found, output [].
    """).strip()


def _hypothesis_prompt(topic: str, context: str) -> str:
    creativity = AGENT_INSTRUCTIONS["hypothesis_creativity"]
    min_sources = AGENT_INSTRUCTIONS["hypothesis_min_evidence_sources"]
    return textwrap.dedent(f"""
        {_system_prompt()}

        Generate research hypotheses about: "{topic}"
        Creativity level: {creativity}

        SUPPORTING CONTEXT:
        {context[:4000]}

        Each hypothesis must be grounded in the provided literature.
        Require at least {min_sources} supporting sources per hypothesis.

        For each hypothesis output JSON with keys:
          hypothesis, supporting_evidence (list of strings),
          opposing_evidence (list of strings),
          confidence (0–1), testability (low/medium/high),
          suggested_methodology.

        Output ONLY a valid JSON array.  Do not wrap in markdown code fences.
    """).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  JSON extraction helper
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Any:
    """Try to extract a JSON array or object from LLM output."""
    # Strip markdown fences
    clean = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    # Find first [ or {
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = clean.find(start_char)
        end   = clean.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(clean[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  ReAct step parser
# ─────────────────────────────────────────────────────────────────────────────

_THOUGHT_RE      = re.compile(r"Thought:\s*(.+?)(?=\nAction:|\nFinal Answer:|$)", re.S)
_ACTION_RE       = re.compile(r"Action:\s*(\w+)\((.+?)\)", re.S)
_OBSERVATION_RE  = re.compile(r"Observation:\s*(.+?)(?=\nThought:|\nFinal Answer:|$)", re.S)
_FINAL_RE        = re.compile(r"Final Answer:\s*(.+)$", re.S)


def _parse_react_output(text: str) -> tuple[list[ReActStep], str]:
    """
    Parse Granite's output into ReAct steps + final answer.
    Handles two cases:
      A) Model followed the format and emitted "Final Answer: ..."
      B) Model responded in plain prose (no format) — treat whole output as answer
    """
    steps: list[ReActStep] = []

    # The prompt already seeds "Thought:" so prepend it to the raw output
    full = "Thought:" + text if not text.lstrip().startswith("Thought:") else text

    for m in _THOUGHT_RE.finditer(full):
        content = m.group(1).strip()
        if content:
            steps.append(ReActStep("thought", content))

    for m in _ACTION_RE.finditer(full):
        try:
            args = json.loads(m.group(2)) if m.group(2).strip().startswith("{") else {}
        except Exception:
            args = {"raw": m.group(2).strip()}
        steps.append(ReActStep("action", f"{m.group(1)}({m.group(2).strip()})",
                                tool=m.group(1), tool_args=args))

    for m in _OBSERVATION_RE.finditer(full):
        obs = m.group(1).strip()
        if obs:
            src = "WEB" if "[WEB" in obs else ("KB" if "[KB" in obs else "INFER")
            steps.append(ReActStep("observation", obs, source=src))

    # Extract final answer — try explicit marker first
    final_m = _FINAL_RE.search(full)
    if final_m:
        final = final_m.group(1).strip()
    else:
        # No "Final Answer:" marker — use the largest non-step paragraph as the answer
        # Strip out all the Thought/Action/Observation lines to get the substance
        cleaned = re.sub(
            r"(Thought:|Action:|Observation:)[^\n]*(\n(?!Thought:|Action:|Observation:|Final Answer:)[^\n]*)*",
            "", full
        ).strip()
        # If cleaned is still empty, fall back to the full raw output
        final = cleaned if len(cleaned) > 20 else text.strip()

    # Ensure at least one step is shown
    if not steps:
        steps.append(ReActStep("thought", "Analysing the query and available context."))

    # Add a visible answer step
    if final:
        steps.append(ReActStep("answer", final[:120] + ("…" if len(final) > 120 else ""),
                                source="INFER"))

    return steps, final


# ─────────────────────────────────────────────────────────────────────────────
#  Main agent
# ─────────────────────────────────────────────────────────────────────────────

class ResearchAgent:
    """Entry point for all agent operations."""

    def __init__(self):
        self.citation_style = AGENT_INSTRUCTIONS["citation_style"]
        self.max_steps      = AGENT_INSTRUCTIONS["react_max_steps"]
        self.threshold      = AGENT_INSTRUCTIONS["confidence_threshold"]

    # ── Core chat query ───────────────────────────────────────────────────────

    def query(self, user_query: str, use_web: bool = True) -> AgentResponse:
        t0 = time.time()
        resp = AgentResponse(query=user_query)

        # 1. Retrieve from KB
        kb_chunks = kb.retrieve(
            user_query, top_k=6, embed_fn=wx.embed if wx.is_configured() else None
        )
        resp.steps.append(ReActStep(
            "observation",
            f"[KB] Retrieved {len(kb_chunks)} relevant chunks from local knowledge base.",
            source="KB",
        ))

        # 2. Always run Exa when web is enabled (supplements KB regardless of score)
        web_results: list[dict] = []
        if use_web and exa.is_configured():
            web_results = exa.search(user_query, num_results=4)
            resp.steps.append(ReActStep(
                "observation",
                f"[WEB] Exa returned {len(web_results)} live results.",
                source="WEB",
            ))

        # 3. Build and send prompt
        prompt = _react_prompt(user_query, kb_chunks, web_results)
        resp.steps.append(ReActStep("thought", "Building ReAct prompt with context."))

        raw_output = wx.generate(
            prompt,
            max_new_tokens=1200,
            temperature=0.3,
            stop_sequences=["User Query:"],
        )

        # 4. Parse ReAct output
        parsed_steps, final_answer = _parse_react_output(raw_output)
        resp.steps.extend(parsed_steps)
        resp.final_answer = final_answer

        # 5. Collect citations from KB chunks used
        seen_titles: set[str] = set()
        citation_idx = 1
        for chunk in kb_chunks:
            if chunk.get("title") not in seen_titles:
                seen_titles.add(chunk["title"])
                resp.citations.append(_format_citation(chunk, citation_idx, self.citation_style))
                citation_idx += 1
        for wr in web_results:
            # Skip error/mock results from citations
            if wr.get("source") in ("WEB_ERROR", "WEB_MOCK") or not wr.get("url"):
                continue
            resp.citations.append(_format_citation(
                {"title": wr["title"], "authors": "Web Source",
                 "year": wr.get("published_date", "")[:4], "url": wr["url"]},
                citation_idx, self.citation_style
            ))
            citation_idx += 1

        resp.elapsed_s = round(time.time() - t0, 2)
        return resp

    # ── Gap analysis ──────────────────────────────────────────────────────────

    def gap_analysis(self) -> list[dict[str, Any]]:
        corpus = kb.get_all_text()
        if not corpus:
            return [{"gap_title": "No papers uploaded",
                     "description": "Upload PDF papers to enable gap analysis.",
                     "missing_evidence": "N/A", "potential_impact": "N/A", "confidence": 0}]

        prompt = _gap_analysis_prompt(corpus)
        raw = wx.generate(prompt, max_new_tokens=1500, temperature=0.4)
        result = _extract_json(raw)
        if isinstance(result, list):
            # Ensure all required keys exist
            for item in result:
                item.setdefault("confidence", 0.7)
                item.setdefault("missing_evidence", "")
                item.setdefault("potential_impact", "")
            return result
        # Fallback: parse plain text into gap cards
        return _text_to_gaps(raw)

    # ── Contradiction detection ───────────────────────────────────────────────

    def contradiction_detection(self) -> list[dict[str, Any]]:
        corpus = kb.get_all_text()
        if not corpus:
            return []

        prompt = _contradiction_prompt(corpus)
        raw = wx.generate(prompt, max_new_tokens=1200, temperature=0.2)
        result = _extract_json(raw)
        if isinstance(result, list):
            for item in result:
                item.setdefault("severity", "medium")
            return result
        return []

    # ── Hypothesis generation ─────────────────────────────────────────────────

    def generate_hypotheses(self, topic: str) -> list[dict[str, Any]]:
        chunks = kb.retrieve(topic, top_k=8, embed_fn=wx.embed if wx.is_configured() else None)
        context = "\n\n".join(c["chunk"] for c in chunks)

        # Supplement with Exa if KB sparse
        if not chunks or max(c.get("score", 0) for c in chunks) < 0.4:
            web = exa.search(topic, num_results=3)
            context += "\n\n" + "\n\n".join(r["text_snippet"] for r in web)

        prompt = _hypothesis_prompt(topic, context)
        raw = wx.generate(prompt, max_new_tokens=1400, temperature=0.5)
        result = _extract_json(raw)
        if isinstance(result, list):
            for h in result:
                h.setdefault("confidence", 0.6)
                h.setdefault("testability", "medium")
                h.setdefault("supporting_evidence", [])
                h.setdefault("opposing_evidence", [])
                h.setdefault("suggested_methodology", "")
            return result
        return _text_to_hypotheses(raw)

    # ── Dashboard summary ─────────────────────────────────────────────────────

    def dashboard_summary(self) -> dict[str, Any]:
        papers = kb.list_papers()
        return {
            "total_papers": len(papers),
            "papers": papers,
            "watsonx_configured": wx.is_configured(),
            "exa_configured": exa.is_configured(),
            "domain": AGENT_INSTRUCTIONS["domain"],
            "citation_style": AGENT_INSTRUCTIONS["citation_style"],
            "react_max_steps": AGENT_INSTRUCTIONS["react_max_steps"],
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Plain-text fallback parsers
# ─────────────────────────────────────────────────────────────────────────────

def _text_to_gaps(text: str) -> list[dict[str, Any]]:
    gaps = []
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    for i, para in enumerate(paragraphs[:8]):
        gaps.append({
            "gap_title": f"Research Gap {i+1}",
            "description": para[:300],
            "missing_evidence": "See description",
            "potential_impact": "Requires further investigation",
            "confidence": 0.6,
        })
    return gaps or [{"gap_title": "Analysis pending", "description": text[:200],
                      "missing_evidence": "", "potential_impact": "", "confidence": 0.5}]


def _text_to_hypotheses(text: str) -> list[dict[str, Any]]:
    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    result = []
    for i, para in enumerate(paras[:5]):
        result.append({
            "hypothesis": para[:300],
            "supporting_evidence": [],
            "opposing_evidence": [],
            "confidence": 0.55,
            "testability": "medium",
            "suggested_methodology": "Experimental validation required",
        })
    return result or [{"hypothesis": text[:300], "supporting_evidence": [],
                        "opposing_evidence": [], "confidence": 0.5,
                        "testability": "low", "suggested_methodology": ""}]


# ── Module-level singleton ────────────────────────────────────────────────────
agent = ResearchAgent()

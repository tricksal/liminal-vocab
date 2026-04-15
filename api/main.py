"""
Liminal Vocab - API

Serves the knowledge graph and receives proposals via web form.
"""

import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .graph import Graph

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "tricksal/liminal-vocab"

graph = Graph()

app = FastAPI(
    title="Liminal Vocab API",
    root_path="/liminal-vocab/api",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://workspace.tricksal.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Graph endpoints ──────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/terms")
async def get_terms(lang: str = "en"):
    return graph.all_terms_resolved(lang)


@app.get("/terms/{term_id}")
async def get_term(term_id: str, lang: str = "en"):
    resolved = graph.resolve_term(term_id, lang)
    if not resolved:
        raise HTTPException(status_code=404, detail="Term not found")
    return resolved


@app.get("/communities")
async def get_communities(lang: str = "en"):
    return graph.all_communities(lang)


@app.get("/patterns")
async def get_patterns(lang: str = "en"):
    return graph.all_patterns(lang)


@app.get("/wanted")
async def get_wanted(lang: str = "en"):
    return graph.all_wanted(lang)


@app.get("/graph")
async def get_graph(lang: str = "en"):
    return graph.graph_data(lang)


@app.post("/reload")
async def reload_graph():
    graph.reload()
    return {"status": "reloaded", "terms": len(graph.get_nodes_by_type("Term"))}


# ── Submission endpoints ──────────────────────────────────────────


async def _create_issue(title: str, body: str, labels: list[str]) -> dict:
    if not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="GitHub token not configured")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"title": title, "body": body, "labels": labels},
        )
    if response.status_code not in (201, 200):
        raise HTTPException(status_code=502, detail="Failed to create GitHub issue")
    data = response.json()
    return {"success": True, "issue_url": data.get("html_url"), "issue_number": data.get("number")}


class TermProposal(BaseModel):
    term: str = Field(..., min_length=1, max_length=200)
    community: str = Field(..., min_length=1, max_length=300)
    makes_visible: str = Field(..., min_length=10, max_length=2000)
    pattern: str = Field("", max_length=500)
    citation: str = Field(..., min_length=10, max_length=3000)
    context: str = Field("", max_length=2000)
    submitter_name: str = Field("", max_length=200)


@app.post("/submit")
async def submit_term(proposal: TermProposal):
    body = f"""## Term Proposal: {proposal.term}

**Submitted via web form**{f" by {proposal.submitter_name}" if proposal.submitter_name else ""}

### Where does it come from?
{proposal.community}

### What does this term make visible?
{proposal.makes_visible}
"""
    if proposal.pattern:
        body += f"\n### What kind of shift does it perform?\n{proposal.pattern}\n"
    body += f"\n### Citation from actual usage\n{proposal.citation}\n"
    if proposal.context:
        body += f"\n### Additional context\n{proposal.context}\n"

    return await _create_issue(f"[Term] {proposal.term}", body, ["term-proposal"])


class WantedProposal(BaseModel):
    description: str = Field(..., min_length=20, max_length=2000)
    tags: str = Field("", max_length=500)
    submitter_name: str = Field("", max_length=200)


@app.post("/wanted/submit")
async def submit_wanted(proposal: WantedProposal):
    body = f"""## Wanted: A word for...

**Submitted via web form**{f" by {proposal.submitter_name}" if proposal.submitter_name else ""}

### Description
{proposal.description}
"""
    if proposal.tags:
        body += f"\n### Tags\n{proposal.tags}\n"

    return await _create_issue("[Wanted] " + proposal.description[:60], body, ["wanted-term"])


class SignalProposal(BaseModel):
    signal_type: str = Field(..., pattern=r"^(citation|sighting|connection|translation|scholarly)$")
    text: str = Field(..., min_length=10, max_length=2000)
    submitter_name: str = Field("", max_length=200)


@app.post("/signal/{term_id}")
async def submit_signal(term_id: str, signal: SignalProposal):
    term = graph.get_node(term_id)
    if not term or term.get("type") != "Term":
        raise HTTPException(status_code=404, detail="Term not found")

    label = term.get("labels", {}).get("en", term_id)
    body = f"""## Signal for: {label}

**Type:** {signal.signal_type}
**Submitted via web form**{f" by {signal.submitter_name}" if signal.submitter_name else ""}

### Evidence
{signal.text}
"""
    return await _create_issue(f"[Signal] {label}: {signal.signal_type}", body, ["signal"])

"""
Liminal Vocab — Submission API

Receives term proposals from the web form and creates GitHub Issues.
"""

import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "tricksal/liminal-vocab"

app = FastAPI(
    title="Liminal Vocab API",
    root_path="/liminal-vocab/api",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://workspace.tricksal.com"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

class TermProposal(BaseModel):
    term: str = Field(..., min_length=1, max_length=200)
    community: str = Field(..., min_length=1, max_length=300)
    makes_visible: str = Field(..., min_length=10, max_length=2000)
    pattern: str = Field("", max_length=500)
    citation: str = Field(..., min_length=10, max_length=3000)
    context: str = Field("", max_length=2000)
    submitter_name: str = Field("", max_length=200)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/submit")
async def submit_term(proposal: TermProposal):
    if not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="GitHub token not configured")

    body = f"""## Term Proposal: {proposal.term}

**Submitted via web form**{f" by {proposal.submitter_name}" if proposal.submitter_name else ""}

### Where does it come from?
{proposal.community}

### What does this term make visible?
{proposal.makes_visible}
"""

    if proposal.pattern:
        body += f"""
### What kind of shift does it perform?
{proposal.pattern}
"""

    body += f"""
### Citation from actual usage
{proposal.citation}
"""

    if proposal.context:
        body += f"""
### Additional context
{proposal.context}
"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "title": f"[Term] {proposal.term}",
                "body": body,
                "labels": ["term-proposal"],
            },
        )

    if response.status_code not in (201, 200):
        raise HTTPException(
            status_code=502,
            detail="Failed to create GitHub issue",
        )

    data = response.json()
    return {
        "success": True,
        "issue_url": data.get("html_url"),
        "issue_number": data.get("number"),
    }

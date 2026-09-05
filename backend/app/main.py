"""The HTTP surface.

Small on purpose. The pipeline is driven from the CLI; what a frontend needs
from the backend today is to know which tracks exist, so it can offer them
rather than hard-coding a use case of its own.

Profiles are JSON on disk precisely so these routes are a passthrough. When a
caller is eventually allowed to adjust a profile at run time, the thing it
sends is the same document shape it reads here.
"""

from fastapi import FastAPI, HTTPException

from app.profiles import load, load_all

app = FastAPI(title="CrazyMonkey API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/profiles")
def profiles() -> list[dict]:
    """Every track, as a picker needs it: identity and shape, not the prompts."""
    return [p.summary() for p in load_all()]


@app.get("/api/profiles/{profile_id}")
def profile(profile_id: str) -> dict:
    try:
        return load(profile_id).summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # A malformed profile is a server-side fault, not a bad request — the
        # caller asked for something that exists and we cannot serve it.
        raise HTTPException(status_code=500, detail=str(exc)) from exc

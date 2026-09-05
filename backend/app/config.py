"""Configuration, read once from the environment.

The model endpoint is deliberately not hard-coded anywhere: it is whatever
`.env` says, and the served model id is read from the endpoint itself rather
than assumed, because a model string copied from another project is the kind
of confidently-wrong value that costs an hour to find.
"""

from __future__ import annotations

import json
import os
import urllib.request
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_user_agent: str = "CrazyMonkey/0.1"
    # The served model is a hybrid reasoning model and thinks by default. Left
    # on, as the server ships it. Set false to spend the tokens on the answer
    # instead — measured: a long prompt with thinking on returned 0 characters
    # after 285s, the same prompt with it off returned 3,400.
    llm_enable_thinking: bool = True

    daytona_api_key: str = ""
    daytona_target: str = "eu"

    agent_max_attempts: int = 4
    agent_max_turns: int = 20
    agent_timeout: int = 300

    @cached_property
    def resolved_model(self) -> str:
        """The served model id, asked for rather than guessed.

        Falls back to `llm_model` when the endpoint cannot be reached, so an
        offline unit test does not have to make a network call.
        """
        if self.llm_model:
            return self.llm_model
        request = urllib.request.Request(f"{self.llm_base_url.rstrip('/')}/models")
        request.add_header("Authorization", f"Bearer {self.llm_api_key}")
        request.add_header("User-Agent", self.llm_user_agent)
        with urllib.request.urlopen(request, timeout=30) as response:
            served = json.load(response)["data"]
        if not served:
            raise RuntimeError(f"{self.llm_base_url} serves no models")
        return served[0]["id"]

    @property
    def litellm_model(self) -> str:
        """LiteLLM routes by prefix. `hosted_vllm/` makes it send its own
        User-Agent, which matters when a CDN in front of the endpoint blocks
        the OpenAI SDK's default one with a 403.
        """
        return f"hosted_vllm/{self.resolved_model}"


def load_settings() -> Settings:
    # A descriptive User-Agent has to reach every request, including ones made
    # by libraries we do not control, so it goes into the environment too.
    settings = Settings()
    os.environ.setdefault("OR_SITE_URL", "")
    return settings

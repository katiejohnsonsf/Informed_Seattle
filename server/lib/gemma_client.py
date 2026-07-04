"""
Gemma client for text generation and summarization.

Uses an OpenAI-compatible chat completions API so callers can point the
client at a hosted Gemma deployment without checking secrets into source
control.
"""

import os
import requests
from django.conf import settings


class GemmaClient:
    """Client for interacting with a hosted Gemma model."""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        model_name: str | None = None,
    ):
        self.api_key = api_key or getattr(settings, "GEMMA_API_KEY", None) or os.environ.get(
            "GEMMA_API_KEY"
        )
        self.api_url = (
            api_url
            or getattr(settings, "GEMMA_API_URL", None)
            or os.environ.get("GEMMA_API_URL")
            or "https://llmaven-prod-litellm-prod.lemonmoss-19296c81.westus2.azurecontainerapps.io/v1"
        ).rstrip("/")
        self.model_name = (
            model_name
            or getattr(settings, "GEMMA_MODEL_NAME", None)
            or os.environ.get("GEMMA_MODEL_NAME")
            or "gemma-4-31b"
        )

        if not self.api_key:
            raise ValueError(
                "GEMMA_API_KEY is not set. Add it to your .env file or environment variables."
            )

    def _chat_completions_url(self) -> str:
        """Return the chat completions endpoint for the configured API URL."""
        if self.api_url.endswith("/chat/completions"):
            return self.api_url
        return f"{self.api_url}/chat/completions"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate text from a prompt via the configured Gemma endpoint."""
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "top_p": top_p,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            self._chat_completions_url(),
            json=payload,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def summarize(
        self,
        text: str,
        style: str = "what_changed",
        **_kwargs,
    ) -> dict:
        """Summarize legislative text via the configured Gemma endpoint."""
        if style == "what_changed":
            prompt = (
                "Please provide a concise summary of the following legislative text.\n"
                "First, create a brief headline (under 10 words), then provide a "
                "2-3 sentence summary.\n\n"
                f"Text to summarize:\n{text}\n\n"
                "Format your response as:\n"
                "HEADLINE: [your headline here]\n"
                "SUMMARY: [your 2-3 sentence summary here]"
            )
        else:
            prompt = (
                "Please summarize the following legislative text.\n"
                "First, create a headline, then provide a detailed summary.\n\n"
                f"Text to summarize:\n{text}\n\n"
                "Format your response as:\n"
                "HEADLINE: [your headline here]\n"
                "SUMMARY: [your detailed summary here]"
            )

        response = self.generate(prompt)

        headline = ""
        body = ""
        if "HEADLINE:" in response and "SUMMARY:" in response:
            parts = response.split("SUMMARY:")
            headline = parts[0].replace("HEADLINE:", "").strip()
            body = parts[1].strip()
        else:
            body = response
            sentences = body.split(".")
            if sentences:
                headline = sentences[0].strip()

        return {"headline": headline, "body": body}


_gemma_client: GemmaClient | None = None


def get_gemma_client() -> GemmaClient:
    """Get or create the global Gemma client instance."""
    global _gemma_client
    if _gemma_client is None:
        _gemma_client = GemmaClient()
    return _gemma_client

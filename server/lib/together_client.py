"""
Together AI client for text generation and summarization.

Calls Together AI's OpenAI-compatible chat completions API, so no heavy
local model weights are needed.  Mirrors the OLMoClient interface so that
server/lib/summary_model.py can swap between the two transparently.
"""

import os
import requests
from django.conf import settings

_TOGETHER_API_URL = "https://api.together.ai/v1/chat/completions"


class TogetherClient:
    """Client for interacting with Together AI hosted models."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or getattr(
            settings,
            "TOGETHER_MODEL",
            "allenai/OLMo-2-1124-13B-Instruct",
        )
        self.api_key = getattr(settings, "TOGETHER_API_KEY", None) or os.environ.get(
            "TOGETHER_API_KEY"
        )
        if not self.api_key:
            raise ValueError(
                "TOGETHER_API_KEY is not set. Add it to your .env file or "
                "environment variables."
            )

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """
        Generate text from a prompt via Together AI.

        Args:
            prompt: Input text (sent as a user message).
            max_new_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.

        Returns:
            Generated text string.
        """
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            _TOGETHER_API_URL, json=payload, headers=headers, timeout=120
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def summarize(
        self,
        text: str,
        style: str = "what_changed",
        max_tokens: int = 256,
    ) -> dict:
        """
        Summarize legislative text via Together AI.

        Args:
            text: Text to summarize (truncated to 4000 chars).
            style: Summarization style name.
            max_tokens: Maximum tokens for the summary.

        Returns:
            Dict with 'headline' and 'body' keys.
        """
        if style == "what_changed":
            prompt = (
                "Please provide a concise summary of the following legislative text.\n"
                "First, create a brief headline (under 10 words), then provide a "
                "2-3 sentence summary.\n\n"
                f"Text to summarize:\n{text[:4000]}\n\n"
                "Format your response as:\n"
                "HEADLINE: [your headline here]\n"
                "SUMMARY: [your 2-3 sentence summary here]"
            )
        else:
            prompt = (
                "Please summarize the following legislative text.\n"
                "First, create a headline, then provide a detailed summary.\n\n"
                f"Text to summarize:\n{text[:4000]}\n\n"
                "Format your response as:\n"
                "HEADLINE: [your headline here]\n"
                "SUMMARY: [your detailed summary here]"
            )

        response = self.generate(prompt, max_new_tokens=max_tokens)

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


_together_client: TogetherClient | None = None


def get_together_client() -> TogetherClient:
    """Get or create the global Together AI client instance."""
    global _together_client
    if _together_client is None:
        _together_client = TogetherClient()
    return _together_client

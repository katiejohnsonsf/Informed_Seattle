"""
OLMo 3 client for text generation and summarization.
"""

import os
from typing import Optional
from server.lib.gemma_client import GemmaClient
from server.lib.together_client import TogetherClient
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

def _get_setting_or_env(name: str):
    value = os.environ.get(name)
    if value is not None:
        return value

    try:
        from django.conf import settings

        return getattr(settings, name, None)
    except Exception:
        return None


def _select_summarization_backend() -> str:
    """
    Select which summarization backend to use.

    Order:
    1. explicit SUMMARIZATION_BACKEND
    2. GEMMA_API_KEY => gemma
    3. TOGETHER_API_KEY => together
    4. fallback => olmo
    """
    backend = (_get_setting_or_env("SUMMARIZATION_BACKEND") or "auto").lower()

    if backend == "auto":
        if _get_setting_or_env("GEMMA_API_KEY"):
            return "gemma"
        if _get_setting_or_env("TOGETHER_API_KEY"):
            return "together"
        return "olmo"

    return backend


def _select_device(requested: Optional[str] = None) -> str:
    """Select the best available device."""
    if requested:
        return requested
    env_device = os.getenv("OLMO_DEVICE")
    if env_device:
        return env_device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class OLMoClient:
    """Client for interacting with OLMo models."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        max_length: int = 2048,
    ):
        self.model_name = model_name or os.getenv(
            "OLMO_MODEL_NAME", "allenai/OLMo-2-0425-1B-Instruct"
        )
        self.device = _select_device(device)
        self.max_length = max_length

        # Load model and tokenizer
        print(f"Loading OLMo model: {self.model_name} on {self.device}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        if self.device == "cuda":
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                dtype=torch.float16,
                device_map="auto",
            )
        else:
            # CPU/MPS: load in float32 (native CPU dtype, no upcasting needed).
            # The 1B model at ~6GB float32 fits comfortably in 16GB RAM.
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                dtype=torch.float32,
            )
            self.device = "cpu"

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """
        Generate text from a prompt using OLMo 3.

        Args:
            prompt: Input prompt
            max_new_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter

        Returns:
            Generated text
        """
        # Format using the tokenizer's chat template
        messages = [{"role": "user", "content": prompt}]
        formatted_prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Tokenize
        inputs = self.tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length - max_new_tokens,
        ).to(self.device)
        input_len = inputs["input_ids"].shape[1]

        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        # Decode only the newly generated tokens
        response = self.tokenizer.decode(
            outputs[0][input_len:], skip_special_tokens=True
        ).strip()

        return response

    def summarize(
        self,
        text: str,
        style: str = "what_changed",
        max_tokens: int = 256,
    ) -> dict:
        """
        Summarize text using OLMo 3.

        Args:
            text: Text to summarize
            style: Summarization style (e.g., 'concise', 'detailed')
            max_tokens: Maximum tokens for summary

        Returns:
            Dictionary with 'headline' and 'body' keys
        """
        # Create summarization prompt
        if style == "what_changed":
            prompt = f"""Please provide a concise summary of the \
following legislative text.
First, create a brief headline (under 10 words), then provide a 2-3 sentence summary.

Text to summarize:
{text[:4000]}

Format your response as:
HEADLINE: [your headline here]
SUMMARY: [your 2-3 sentence summary here]"""
        else:
            prompt = f"""Please summarize the following legislative text.
First, create a headline, then provide a detailed summary.

Text to summarize:
{text[:4000]}

Format your response as:
HEADLINE: [your headline here]
SUMMARY: [your detailed summary here]"""

        # Generate summary
        response = self.generate(prompt, max_new_tokens=max_tokens)

        # Parse response
        headline = ""
        body = ""

        if "HEADLINE:" in response and "SUMMARY:" in response:
            parts = response.split("SUMMARY:")
            headline = parts[0].replace("HEADLINE:", "").strip()
            body = parts[1].strip()
        else:
            # Fallback: treat entire response as body
            body = response
            # Try to extract first sentence as headline
            sentences = body.split(".")
            if sentences:
                headline = sentences[0].strip()

        return {
            "headline": headline,
            "body": body,
        }


# Global instance (lazy loaded)
_olmo_client: OLMoClient | GemmaClient | TogetherClient | None = None


def get_olmo_client():
    """
    Get or create the global summarization client.

    Despite the legacy name, this now returns the configured backend client:
    - gemma
    - together
    - olmo
    """
    global _olmo_client
    if _olmo_client is None:
        backend = _select_summarization_backend()

        if backend == "gemma":
            from server.lib.gemma_client import get_gemma_client

            _olmo_client = get_gemma_client()

        elif backend == "together":
            from server.lib.together_client import get_together_client

            _olmo_client = get_together_client()

        elif backend == "olmo":
            _olmo_client = OLMoClient()

        else:
            raise ValueError(
                "Unsupported SUMMARIZATION_BACKEND. "
                "Use one of: auto, gemma, together, olmo."
            )

    return _olmo_client
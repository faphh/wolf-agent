"""Wolf Providers — Auto-import all provider modules to trigger registration."""

from wolf.providers.base import Provider, create_provider, register_provider

# Import provider modules to trigger registration
try:
    from wolf.providers import anthropic_provider  # noqa: F401
except ImportError:
    pass

try:
    from wolf.providers import openai_provider  # noqa: F401
except ImportError:
    pass

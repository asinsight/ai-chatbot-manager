import tiktoken

# Load encoding once at module level
_encoding = tiktoken.encoding_for_model("gpt-4")

# Per-message overhead tokens (role / content separators, etc.)
_TOKENS_PER_MESSAGE = 4


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Return the token count for the given text."""
    if model == "gpt-4":
        enc = _encoding
    else:
        enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    """Compute the total token count across the messages list.

    Sums each message's role + content tokens and adds roughly 4 tokens of
    overhead per message.
    """
    total = 0
    for msg in messages:
        total += _TOKENS_PER_MESSAGE
        total += len(_encoding.encode(msg.get("role", "")))
        total += len(_encoding.encode(msg.get("content", "")))
    # Tokens for priming the assistant response
    total += 3
    return total


def trim_history(messages: list[dict], max_tokens: int) -> list[dict]:
    """Trim the oldest messages to fit within the token budget (max_tokens).

    Removes from the front (oldest first) and always keeps at least one message.
    """
    while len(messages) > 1 and count_messages_tokens(messages) > max_tokens:
        messages = messages[1:]
    return messages

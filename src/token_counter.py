import tiktoken

# 모듈 레벨에서 인코딩 한번만 로드
_encoding = tiktoken.encoding_for_model("gpt-4")

# 메시지당 오버헤드 토큰 수 (role, content 구분자 등)
_TOKENS_PER_MESSAGE = 4


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """텍스트의 토큰 수를 반환한다."""
    if model == "gpt-4":
        enc = _encoding
    else:
        enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    """messages 배열 전체의 토큰 수를 계산한다.

    각 메시지의 role + content 토큰을 합산하고,
    메시지당 약 4토큰 오버헤드를 추가한다.
    """
    total = 0
    for msg in messages:
        total += _TOKENS_PER_MESSAGE
        total += len(_encoding.encode(msg.get("role", "")))
        total += len(_encoding.encode(msg.get("content", "")))
    # 어시스턴트 응답 프라이밍용 토큰
    total += 3
    return total


def trim_history(messages: list[dict], max_tokens: int) -> list[dict]:
    """토큰 예산(max_tokens) 내에 맞도록 오래된 메시지부터 잘라낸다.

    앞에서부터(오래된 것부터) 제거하며, 최소 1개 메시지는 유지한다.
    """
    while len(messages) > 1 and count_messages_tokens(messages) > max_tokens:
        messages = messages[1:]
    return messages

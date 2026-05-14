import time

retriever = None
_start_time = time.time()
guild_thread_mode: dict[int, bool] = {}
anthropic_cooldowns: dict[int, float] = {}
local_cooldowns: dict[int, float] = {}
query_terms: list[str] = []

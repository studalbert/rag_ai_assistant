from slowapi import Limiter
from slowapi.util import get_remote_address

# key_func=get_remote_address — лимитируем по IP. Когда дойдём до Nginx (Этап 8),
# нужно будет убедиться, что он правильно прокидывает реальный IP клиента
# (X-Forwarded-For), иначе все запросы из-за прокси будут считаться одним IP.
limiter = Limiter(key_func=get_remote_address)
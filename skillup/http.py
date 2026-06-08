import truststore
import requests

truststore.inject_into_ssl()

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session

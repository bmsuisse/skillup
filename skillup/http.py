from functools import cache

import requests
import truststore

truststore.inject_into_ssl()


@cache
def session() -> requests.Session:
    return requests.Session()

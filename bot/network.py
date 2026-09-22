import ssl

import certifi


def tls_context():
    """Portable Mozilla CA bundle; never depend on an empty Python/system certificate store."""
    return ssl.create_default_context(cafile=certifi.where())

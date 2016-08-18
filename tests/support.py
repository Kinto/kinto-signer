try:
    from kinto.testing import BaseWebTest, get_user_headers
except ImportError:
    # kinto <= 4.0.0
    from kinto.tests.support import BaseWebTest, get_user_headers  # NOQA

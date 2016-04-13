from kinto import logger

from .local_ecdsa import ECDSASigner
from .autograph import AutographSigner
from .exceptions import BadSignatureError


__all__ = ("ECDSASigner", "BadSignatureError", "AutographSigner")


def heartbeat(request):
    """Test that signer is operationnal.

    :param request: current request object
    :type request: :class:`~pyramid:pyramid.request.Request`
    :returns: ``True`` is everything is ok, ``False`` otherwise.
    :rtype: bool
    """
    signer = request.registry.signer
    try:
        result = signer.sign("TEST")
        expected = set(["signature", "hash_algorithm", "signature_encoding"])
        if len(expected.intersection(result.keys())) != 3:
            raise ValueError("Invalid response content: %s" % result)
        return True
    except Exception as e:
        logger.exception(e)
        return False

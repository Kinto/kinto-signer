from kinto import logger


EXPECTED_FIELDS = ["content-signature", "signature", "hash_algorithm",
                   "signature_encoding", "x5u"]


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
        expected = set(EXPECTED_FIELDS)
        if len(expected.intersection(result.keys())) != len(EXPECTED_FIELDS):
            raise ValueError("Invalid response content: %s" % result)
        return True
    except Exception as e:
        logger.exception(e)
        return False

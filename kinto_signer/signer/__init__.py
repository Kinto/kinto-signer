from kinto import logger


EXPECTED_FIELDS = ["signature", "x5u", "mode"]


def heartbeat(request):
    """Test that signer is operationnal.

    :param request: current request object
    :type request: :class:`~pyramid:pyramid.request.Request`
    :returns: ``True`` is everything is ok, ``False`` otherwise.
    :rtype: bool
    """
    for signer in request.registry.signers.values():
        try:
            result = signer.sign("This is an heartbeat tests.")
            expected = set(EXPECTED_FIELDS)
            obtained = result.keys()
            if len(expected.intersection(obtained)) != len(EXPECTED_FIELDS):
                raise ValueError("Invalid response content: %s" % result)
        except Exception as e:
            logger.exception(e)
            return False
    return True

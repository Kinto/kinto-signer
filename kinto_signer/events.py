class BaseEvent(object):
    def __init__(self, request, payload, impacted_records, resource, original_event):
        self.request = request
        self.payload = payload
        self.impacted_records = impacted_records
        self.resource = resource
        self.original_event = original_event


class ReviewRequested(BaseEvent):
    pass


class ReviewRejected(BaseEvent):
    pass


class ReviewApproved(BaseEvent):
    pass

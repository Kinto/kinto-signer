class BaseEvent(object):
    def __init__(self, request, payload, impacted_objects, resource, original_event):
        self.request = request
        self.payload = payload
        self.impacted_objects = impacted_objects
        self.resource = resource
        self.original_event = original_event

    @property
    def impacted_records(self):
        return self.impacted_objects


class ReviewRequested(BaseEvent):
    pass


class ReviewRejected(BaseEvent):
    pass


class ReviewApproved(BaseEvent):
    pass

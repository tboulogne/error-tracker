# -*- coding: utf-8 -*-
#
#    Django error tracker middleware responsible for recording exception
#
#    :copyright: 2019 Sonu Kumar
#    :license: BSD-3-Clause
#

from error_tracker.django import get_masking_module, get_context_builder, get_ticketing_module, \
    get_exception_model, get_notification_module, APP_ERROR_SUBJECT_PREFIX, APP_ERROR_EMAIL_SENDER, \
    APP_ERROR_RECIPIENT_EMAIL, TRACK_ALL_EXCEPTIONS
from error_tracker.libs.utils import get_exception_name, get_context_detail, get_notification_subject

model = get_exception_model()
ticketing = get_ticketing_module()
masking = get_masking_module()
notifier = get_notification_module()
context_builder = get_context_builder()


# noinspection PyMethodMayBeStatic
class ErrorTracker(object):
    """
     ErrorTracker class, this is responsible for capturing exceptions and
     sending notifications and taking other actions,
    """

    @staticmethod
    def _send_notification(request, message, exception, error):
        """
        Send notification to the list of entities or call the specific methods
        :param request: request object
        :param message: message having frame details
        :param exception: exception that's triggered
        :param error:  error model object
        :return: None
        """
        if notifier is None:
            return
        if request is not None:
            method = request.method
            url = request.get_full_path()
        else:
            method = ""
            url = ""
        subject = get_notification_subject(APP_ERROR_SUBJECT_PREFIX,
                                           method, url, exception)
        notifier.notify(request,
                        error,
                        email_subject=subject,
                        email_body=message,
                        from_email=APP_ERROR_EMAIL_SENDER,
                        recipient_list=APP_ERROR_RECIPIENT_EMAIL)

    @staticmethod
    def _raise_ticket(request, error):
        if ticketing is None:
            return
        ticketing.raise_ticket(request, error)

    @staticmethod
    def _post_process(request, frame_str, frames, error):
        if request is not None:
            message = ('URL: %s' % request.path) + '\n\n'
        else:
            message = ""
        message += frame_str
        ErrorTracker._send_notification(request, message, frames[-1][:-1], error)
        ErrorTracker._raise_ticket(request, error)

    def record_exception(self, request, exception):
        """
        Record the exception details and do post processing actions. this method can be used to track any exceptions,
        even those are being excepted using try/except block.
        :param request:  request object
        :param exception: what type of exception has occurred
        :return:  None
        """
        if request is not None:
            path = request.path
            host = request.META.get('HTTP_HOST', '')
            method = request.method
        else:
            path = ""
            host = ""
            method = ""

        ty, frames, frame_str, traceback_str, rhash, request_data = \
            get_context_detail(request, masking, context_builder)
        error = model.create_or_update_entity(rhash, host, path, method,
                                              str(request_data),
                                              get_exception_name(ty),
                                              traceback_str)
        ErrorTracker._post_process(request, frame_str, frames, error)


# use this object to track errors in the case of custom failures, where try/except is used
error_tracker = ErrorTracker()


def track_exception(func):
    """
    Decorator to be used for automatic exception capture
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as ex:
            error_tracker.record_exception(None, ex)
            raise ex

    return wrapper


class ExceptionTrackerMiddleWare(ErrorTracker):
    """
    Error tracker middleware that's invoked in the case of exception occurs,
    this should be placed at the end of Middleware lists
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if exception is None and not TRACK_ALL_EXCEPTIONS:
            return
        self.record_exception(request, exception)
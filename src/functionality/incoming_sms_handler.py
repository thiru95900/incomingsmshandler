import sys

from celery import current_task
from sm_models.inbound_numbers import InboundNumber, MultichannelInboundNumber

from src.config import METERING
from src.functionality.media import upload_media
from src.functionality.metering import Metering
from src.functionality.sync import IncomingSMSSync
from src.models.incoming_sms import *
from src.utils.config_loggers import log, log_json
from src.utils.constants import SF_STORAGE


class IncomingSMSHandler(object):
    """
    Incoming requests should not be marshalled. All inputs from provider should
    be stored in incoming_sms table
    """

    def __init__(self, params):
        log.info('In constructor of IncomingSMSHandler')
        self.params = params
        self.shortcode = self._remove_plus(params['shortCode'])
        current_task.request.kwargs['short_code'] = self.shortcode
        self.mobile_number = self._remove_plus(params['mobilenumber'])
        self.provider_id = params['providerId']
        self.message = params['message'].encode('UTF-8')
        if type(self.message) == bytes and sys.version_info[0] >= 3:
            self.message = self.message.decode()
        # Even if there is no keyword set in params, set empty string because
        # subscription worker needs it that way.
        self.keyword = params.get('keyword', '')
        self.sub_keyword = params.get('subKeyword', '')
        self.inbound_number_info = {}
        self.incoming_config = {}
        self.is_message_complete = True
        self.error = None
        # If any exception happens, we don't want any partial database
        # transactions to be happened. Commit only when it is in consistent
        # stage.
        self.commit = False
        self.entry_id = params.get('entry_id') or ''
        log.info(f'Celery task id: {self.entry_id}')
        log_json.debug(f"Celery task id: {self.entry_id}")

        # Update values in params
        self.params['shortCode'] = self.shortcode
        self.params['mobilenumber'] = self.mobile_number
        self.params["message"] = self.message
        self.params["keyword"] = self.keyword
        self.params["subKeyword"] = self.sub_keyword
        self.params['totalParts'] = self._total_parts(params.get('totalParts'))

    def process(self):
        try:
            # Update CeleryTask to 'STARTED' status
            self._start_celery_task()

            # From short-code, get inbound number.
            self._get_inbound_number()

            # If inbound number is shared between accounts, parse the message
            # and get keyword and sub-keyword.Add keywords to the message params
            self._handle_shared_number()

            # Based on inbound number and keywords, find account-id. Add account
            # id to the message params
            self._get_incoming_config()

            # Updates the Duplicate Incoming Check For Account. By updating the
            # ttl expiry of the redis key for incoming messages.
            self._update_duplicate_incoming_redis_key()

            # If sms is multipart,
            self._save_part_of_message()

            # If all parts of the message are not yet received, defer further
            # process
            if not self.is_message_complete:
                self.commit = True
                return

            # Handle MMS - Add urls of uploaded media to the message params
            self._upload_media_data()

            # Store incoming SMS to database. Add sms-id to the message params
            log.info("About to save message")
            self._save_message()
            log.info("Processed till save message")

            # Commit all the transactions happened to the database
            self.commit = True
            # Process multichannel metering
            self._metering()
            # Push to channels
            self._push_to_channels()

            # After multipart message has been assembled, update parts records
            # with final sms-id. All parts are still maintained for audit and
            # debugging purpose.
            self._update_parts_of_message()

        except Exception as e:
            log.exception(f"Exception occurred while processing incoming "
                          f"message - {e}")
            log_json.exception("Exception occurred while processing Incoming "
                               "Message", extra={'error': str(e)})
            self.error = str(e)
            db_model.rollback_session()
        finally:
            # Complete the CeleryTask
            if self.error:
                self._fail_celery_task(error=self.error)
            else:
                self._complete_celery_task()

    def _start_celery_task(self):
        start_celery_task(entry_id=self.entry_id)

    def _get_inbound_number(self):
        log.info('Inside function _get_inbound_number')
        table_source = InboundNumber
        channel_type = self.params.get('channel_type')
        is_multichannel = check_multichannel(channel_type)
        if is_multichannel or not self.shortcode.isnumeric():
            table_source = MultichannelInboundNumber

        # Setting up table_source in params. Its required for metering.
        # NOTE: DO NOT REMOVE IT.
        self.params['table_source'] = table_source
        self.inbound_number_info = get_inbound_number(self.shortcode,
                                                      self.provider_id,
                                                      table_source)

    def _handle_shared_number(self):
        log.info('Inside function _handle_shared_number')
        if not is_shared_number(self.inbound_number_info):
            log_json.debug(f"Inbound number:{self.shortcode} is not shared "
                           f"number")
            return

        keyword, sub_keyword = get_keywords(self.message)
        log_json.debug(f"Inbound number: {self.shortcode} is a shared "
                       f"number. keyword = {keyword} and sub_keyword = "
                       f"{sub_keyword}")

        if not self.params.get("keyword"):
            self.params["keyword"] = self.keyword = keyword
        if not self.params.get("subKeyword"):
            self.params["subKeyword"] = self.sub_keyword = sub_keyword

    def _get_incoming_config(self):
        log.info('Inside function _get_incoming_config')
        self.incoming_config = get_incoming_config(self.shortcode, self.keyword)
        self.params['accountId'] = self.incoming_config['account_id']
        current_task.request.kwargs['account_id'] = self.params['accountId']

    def _update_duplicate_incoming_redis_key(self):
        log.debug("Inside Function of _update_duplicate_incoming_redis_key")
        duplicate_key = self.params.get('duplicate_incoming_redis_key')
        if duplicate_key:
            account_id = self.params.get('accountId')
            update_duplicate_incoming_expiry(account_id, duplicate_key)
        else:
            log.info('No duplicate_incoming_redis_key found in params')

    def _save_part_of_message(self):
        log.info('Inside function _save_part_of_message')
        # TODO sms central
        if not self._is_multipart_message():
            return

        self.is_message_complete = False
        log.debug("Message is a multipart message")
        parts_count = get_count_of_parts(self.params)
        log.info(f'Parts received so far: {parts_count}')
        extra = {
            "message_id": self.params.get("messageId", None),
            "is_multi_part": self.params.get("isMultiPart", None),
            'total_parts': self.params.get("totalParts"),
            'part_number': parts_count
        }
        log_json.debug("Message is a multipart message", extra=extra)
        save_incoming_message_part(self.params)
        if are_all_parts_received(self.params, parts_count):
            log_json.debug("All parts received", extra={
                'totalParts': self.params.get("totalParts")})

            message = assemble_message(self.params)
            if message:
                self.params["message"] = message
                self.is_message_complete = True

    def _upload_media_data(self):
        log.info('Inside function _upload_media_data')
        account_id = self.params.get("accountId")
        if self.params.get("mms_urls", []):
            # SMP-14078 HIPAA MMS
            if is_account_hipaa_enabled(account_id):
                log.info("MMS not uploaded to S3 due to HIPAA compliance")
                log_json.info("MMS not uploaded to S3 due to HIPAA compliance.")

                self.params["mms_urls"] = list(
                    filter(None, self.params["mms_urls"]))
            else:
                storage_setting = get_storage_setting(account_id)
                if storage_setting == SF_STORAGE:
                    self.params['skip_db_url_storage'] = True
                else:
                    uploaded_mms_urls = upload_media(self.params["mms_urls"],
                                                     self.params["accountId"],
                                                     self.params.get(
                                                         "providerName"))
                    self.params["mms_urls"] = uploaded_mms_urls

    def _save_message(self):
        log.info('Inside function _save_part_of_message')
        sms_record = save_incoming_sms(self.params)
        self.params["sms_id"] = sms_record["id"]
        self.params["created_on"] = sms_record["created_on"]
        log_json.debug(f"Saved message id = {self.params['sms_id']}")
        log.warning(f"Saved message id: {self.params['sms_id']}")
        return sms_record

    def _metering(self):
        log.info(f'Inside function _metering: METERING={METERING}')
        if not int(METERING):
            return
        Metering().publish_usage_event_details(**self.params)

    def _push_to_channels(self):
        log.info('Inside function _push_to_channels')
        IncomingSMSSync(self.params, self.incoming_config).push()

    def _update_parts_of_message(self):
        log.info('Inside function _update_parts_of_message')

        if not self._is_multipart_message() and \
                not self.params.get('isCronRequest'):
            return

        if not self.is_message_complete:
            return

        update_parts_of_message_after_assembly(self.params)

    def _is_multipart_message(self):
        # Check if message is multi parts or not
        _a = self.params.get('isMultiPart', False)
        _b = self.params.get('totalParts') > 1
        return _a and _b

    def _fail_celery_task(self, error=None):
        fail_celery_task(entry_id=self.entry_id, error=error)

    def _complete_celery_task(self):
        complete_celery_task(entry_id=self.entry_id)

    @staticmethod
    def _remove_plus(code):
        return code[1:] if code.startswith('+') else code

    @staticmethod
    def _total_parts(total_parts):
        return int(total_parts) if str(total_parts).isnumeric() else 1


if __name__ == '__main__':
    data = {
        "mobilenumber": "9922000602",
        "providerId": 1,
        "messageId": 111,
        "message": "SMS magic Beatles" * 10,
        "shortCode": "14242387011",
        "totalParts": 2
    }
    IncomingSMSHandler(data).process()

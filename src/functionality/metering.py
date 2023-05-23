import json
from datetime import datetime

from send_task.process_usage_event import ProcessUsageEvent

from src import config
from src.config import SQLALCHEMY_DATABASE_URI, BROKER_URL
from src.models.metering import *
from src.utils.config_loggers import log, log_json
from src.utils.constants import sender_id_type_map


class Metering(object):

    def publish_usage_event_details(self, **kwargs):
        log.info("Inside function publish_usage_event_details")
        try:
            customer_id, billing_eid, core_subscribed = \
                self.get_billing_customer_details(kwargs.get('accountId'))
            # available balance is not used
            _, credit_bucket_id = self.get_billing_account_balance_info(
                kwargs.get('accountId'), core_subscribed)

            channel_message_type = 'mms' if len(
                kwargs.get('mms_urls', [])) > 0 else 'sms'
            country_id, sender_id_type = self.get_sender_id_type(
                kwargs.get('table_source'), kwargs.get('shortCode'))

            usage_event = dict(
                sms_id=kwargs.get('sms_id'),
                account_id=int(kwargs.get('accountId')),
                customer_id=customer_id,
                billing_eid=billing_eid,
                credit_bucket_id=credit_bucket_id,
                sender_id_type=sender_id_type,
                country_name=get_country_name(country_id),
                provider_name=get_provider_name(kwargs['providerId']),
                event_count=len(kwargs['message']),
                event_type=channel_message_type,
                event_direction=1,
                event_created_date=datetime.now().isoformat(),
                user_id=str(kwargs.get('user_id')),
                event_source=int(kwargs.get('source', 0)),
                # campaignId: None in case of Incoming SMS
                campaign_id=int(kwargs.get('campaign_id', 0)),
                created_on=datetime.now().isoformat(),
                modified_on=datetime.now().isoformat(),
                # In channel details, channel meta info is passed to billing
                # system. It will be stored in billing_event_metering table. It
                # will be forwarded to onebill as and when required.
                channel_details=json.dumps({
                    'channel_type': kwargs.get('channel_type', 'sms'),
                    'message_type': channel_message_type,
                    'metering_type': get_metering_type(
                        kwargs.get('channel_type', 'sms'),
                        channel_message_type
                    ),
                    'total_parts': kwargs.get('totalParts')
                }),
                sent=kwargs.get('sent'),
                core_subscribed=core_subscribed,
                tpi=is_tpi(kwargs.get('shortCode'))
            )
            self.add_usage_event(**usage_event)
        except Exception as e:
            log.error(f'Error while publishing metering event: {e}')
            log_json.exception('Error while publishing metering event',
                               extra={'error': str(e)})

    @staticmethod
    def add_usage_event(**kwargs):
        log.info("Inside function add_usage_event")
        now = datetime.now().isoformat()
        kwargs.update(created_on=now)
        kwargs.update(modified_on=now)
        send_task_event_payload_obj = ProcessUsageEvent(
            database_url=SQLALCHEMY_DATABASE_URI,
            broker_url=BROKER_URL,
            logger_name=config.DEFAULT_LOGGER_NAME)
        send_task_event_payload_obj.send_task(payload=kwargs)

    @staticmethod
    def get_sender_id_type(table_source, sender_id):
        log.info("Inside function get_sender_id_type")
        country_id, sender_id = get_sender_id_type(table_source, sender_id)
        return country_id, sender_id_type_map.get(sender_id, "longcode")

    @staticmethod
    def get_billing_customer_details(account_id):
        log.info("Inside function get_billing_customer_details")
        customer_details = get_customer_and_is_core_details(account_id)
        customer_id = customer_details.get("customer_id")
        billing_external_eid = customer_details.get("billing_external_eid")
        core_subscribed = customer_details.get("core_subscribed")
        return customer_id, billing_external_eid, core_subscribed

    @staticmethod
    def get_billing_account_balance_info(account_id, core_subscribed):
        log.info('Inside function get_billing_account_balance_info')
        if core_subscribed:
            available_balance, balance_bucket_id = \
                check_sufficient_balance_available(account_id)
            log.info(f'balance bucket id-{balance_bucket_id}')
        else:
            available_balance, balance_bucket_id = None, None

        return available_balance, balance_bucket_id

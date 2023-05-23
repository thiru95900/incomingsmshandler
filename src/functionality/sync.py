import json
from copy import deepcopy
from time import mktime, strptime

from celery import current_task
from send_task import SendTask
from sm_utils.utils import function_logger, generate_payload_for_crm

from src import config
from src.config import SQLALCHEMY_DATABASE_URI, BROKER_URL, get_worker_config, \
    CELERY_CONFIG
from src.models.account import is_push_enabled_account, \
    get_account_id_or_parent_id, is_saas_converse_desk_enabled
from src.models.database import db_model
from src.models.incoming_sms import is_account_hipaa_enabled
from src.utils.config_loggers import log, log_json
from src.utils.constants import *
from src.utils.helper import handle_exceptions, insensitive_data, map_keys
from src.utils.message_event import MessageEvent


class SendSyncTask(object):

    def __init__(self):
        self.send_task_obj = SendTask(
            database_url=SQLALCHEMY_DATABASE_URI,
            broker_url=BROKER_URL, **CELERY_CONFIG,
            request_id=current_task.request.id,
            logger_name=config.DEFAULT_LOGGER_NAME
        )

    def send_with_payload(self, account_id, worker, payload):
        func = self.send_task_obj.generic_send_task
        return self._send(account_id, worker, payload, func)

    def send_with_entry_id(self, worker, payload):
        func = self.send_task_obj.generic_send_task_arg_entry_id
        account_id = payload.get('account_id')
        return self._send(account_id, worker, payload, func)

    def _send(self, account_id, worker, payload, func):
        worker_config = self._get_worker_config(worker)
        result = func(
            payload=payload,
            **worker_config
        )
        return self._update_task(account_id, result)

    @staticmethod
    def _get_worker_config(worker):
        return get_worker_config(worker)

    @staticmethod
    def _update_task(account_id, result):
        task, entry_id = result
        log.info(f'Inside function _update_task = {task}, {entry_id}')
        is_hipaa = is_account_hipaa_enabled(account_id)
        db_model.update_celery_task_id(is_hipaa, entry_id, task)
        return True


class IncomingSMSSync(object):

    def __init__(self, message, account_config):
        self.message = deepcopy(message)
        self.account_config = account_config
        self.send_sync_task = SendSyncTask()
        # Fetch parent account details if auth is not  set for this account
        self.set_account_with_valid_auth()
        self.account_id = int(self.message.get('accountId'))

    def push(self):
        log.info('Inside function IncomingSMSSync.push')
        log.info(f'Push to channels for account :{self.account_id}')

        # Usual channels to push incoming messages
        self.push_to_mobile()
        self.push_to_bot()
        self.push_to_subscription()
        self.push_to_converse_desk()

        # Platform specific channels to push incoming messages
        sync_map = {
            'sf': self.push_to_salesforce,
            'zoho': self.push_to_zoho,
            'bullhorn': self.push_to_bullhorn,
            'url': self.push_to_url,
            'email': self.push_to_email,
            'live_chat': self.push_to_live_chat
        }

        for channel, sync_func in sync_map.items():
            if self.account_config.get(f'push_to_{channel}'):
                sync_func()

    @handle_exceptions
    def push_to_mobile(self):
        log.info('Inside function IncomingSMSSync.push_to_mobile')
        if not is_push_enabled_account(account_id=self.account_id):
            log.info("Push to mobile notification skipped")
            return None
        payload = self._get_payload_for_mobile()
        self.send_task(CHANNEL_MOBILE, payload)

    @handle_exceptions
    def push_to_bot(self):
        log.info('Inside function IncomingSMSSync.push_to_bot')
        if not self._is_bot_enabled_for_incoming_number():
            return
        # If Converse Desk is enabled then route messages through the Converse
        # Desk
        if is_saas_converse_desk_enabled(account_id=self.account_id):
            return

        payload = self._get_payload_for_bot()
        self.send_task(CHANNEL_BOT, payload)

    @handle_exceptions
    def push_to_subscription(self):
        log.info('Inside function IncomingSMSSync.push_to_subscription')
        if not self._is_subscription_mgmt_enabled():
            return
        if not is_saas_converse_desk_enabled(account_id=self.account_id):
            payload = self._get_payload_for_subscription()
            self.send_task(CHANNEL_SUBSCRIPTION, payload)

    @handle_exceptions
    def push_to_converse_desk(self):
        log.info('Inside function IncomingSMSSync.push_to_converse_desk')
        if is_saas_converse_desk_enabled(account_id=self.account_id):
            return MessageEvent().in_event(
                self.message.get("sms_id"),
                subscription_payload=self._get_payload_for_auto_reply(),
                bot_status=self._is_bot_enabled_for_incoming_number()
            )
        log.info("Push to conversation desk notification skipped")
        return self.push_to_auto_reply_business_hour()

    @handle_exceptions
    def push_to_auto_reply_business_hour(self):
        log.info('Inside function IncomingSMSSync.push_to_auto_'
                 'reply_business_hour')
        self.send_task(CHANNEL_AUTO_REPLY, self._get_payload_for_auto_reply())
        log.info("sent task for auto reply")
        return True

    @handle_exceptions
    def push_to_salesforce(self):
        log.info('Inside function IncomingSMSSync.push_to_salesforce')
        self.message.update(bot_status=self.account_config.get('bot_status'))
        payload = self._get_payload_for_salesforce()
        log_json.info(f'Sending data to push to Salesforce: '
                      f'{CHANNEL_SALESFORCE_PUSH}')

        channel_type = payload.get('channel_type')
        if payload.get('event_type') and channel_type in ['line', 'viber']:
            log.info("Sending Line Viber event details to salesforce_push")
            payload.update(request_type=SYNC_CHANNEL_EVENTS_REQUEST_TYPE)
            self.send_task(CHANNEL_SALESFORCE_PUSH, payload)
        else:
            self.send_task(CHANNEL_SALESFORCE, payload)

    @handle_exceptions
    def push_to_zoho(self):
        log.info('Inside function IncomingSMSSync.push_to_zoho')
        payload = self._get_payload_for_zoho()
        log_json.info(f'Sending data to push to zoho: {CHANNEL_PUSH_TO_ZOHO}')
        self.send_task(CHANNEL_PUSH_TO_ZOHO, payload)

    @handle_exceptions
    def push_to_bullhorn(self):
        log.info('Inside function IncomingSMSSync.push_to_bullhorn')
        payload = self._get_payload_for_bullhorn()
        log_json.info(f'Sending data to push to Bullhorn: {CHANNEL_BULLHORN}')
        self.send_task(CHANNEL_BULLHORN, payload)

    @handle_exceptions
    def push_to_url(self):
        log.info('Inside function IncomingSMSSync.push_to_url')
        # Get config from incoming config for Push Incoming SMS to URL.
        payload = self._get_payload_for_url_from_incoming_config()
        log_json.info(f'Sending data to push to URL: {CHANNEL_URL}')

        if (not payload.get('url') or not payload.get('request_type')) and \
                self._is_push_to_url_enabled():
            # If enabled, get the account level setting for Push Incoming SMS
            # to URL.
            payload = self._get_payload_for_url_from_account_config()

        self.send_task(CHANNEL_URL, payload)

    @handle_exceptions
    def push_to_email(self):
        log.info('Inside function IncomingSMSSync.push_to_email')
        payload = self._get_payload_for_email()
        log_json.info(f'Sending data to push to email: {CHANNEL_EMAIL}')
        self.send_task(CHANNEL_EMAIL, payload)

    @handle_exceptions
    def push_to_live_chat(self):
        log.info('Inside function IncomingSMSSync.push_to_live_chat')
        if not self._is_livechat_enabled():
            return
        payload = self._get_payload_for_livechat()
        self.send_task(CHANNEL_LIVE_CHAT, payload, arg='entry_id')

    def send_task(self, worker, payload, audit=True, arg='payload'):
        log.info('Inside function IncomingSMSSync.send_task')
        if arg == 'payload':
            result = self.send_sync_task.send_with_payload(self.account_id,
                                                           worker, payload)
        elif arg == 'entry_id':
            result = self.send_sync_task.send_with_entry_id(worker, payload)
        else:
            log_json.error(f"error while sending task to worker :{worker} i.e "
                           f"arg not supported")
            raise ValueError('Send-Task: arg not supported')

        if audit:
            self.audit(worker)
        return result

    def audit(self, channel):
        log.info('Inside function IncomingSMSSync.audit')
        db_model.audit_sync(self.account_id, self.message['sms_id'], channel)

    @function_logger(log)
    def set_account_with_valid_auth(self):
        params = {'account_id': int(self.message['accountId'])}
        account_id = get_account_id_or_parent_id(**params)
        log.info(f'Account-id is set to {account_id}')
        self.message['accountId'] = account_id

    def _is_bot_enabled_for_incoming_number(self):
        log.info('Inside function _is_bot_enabled_for_incoming_number')
        # We don't want to send incoming message to Chatbot which are keywords
        if self.message.get('message') == self.message.get('keyword'):
            return False
        return bool(self.account_config.get("bot_status"))

    def _is_subscription_mgmt_enabled(self):
        log.info('Inside function _is_subscription_mgmt_enabled')
        tag_name = 'subscription_management'
        return db_model.get_account_tag(self.account_id, tag_name)

    def _is_livechat_enabled(self):
        log.info('Inside function _is_livechat_enabled')
        tag_name = 'isLiveChatEnabled'
        return db_model.get_account_tag(self.account_id, tag_name)

    def _is_push_to_url_enabled(self):
        log.info('Inside function _is_push_to_url_enabled')
        tag_name = 'push_incoming_to_url'
        return db_model.get_account_tag(self.account_id, tag_name)

    def _get_payload_for_mobile(self):
        log.info('Inside function _get_payload_for_mobile')
        key_map = {
            'message': 'sms_text',
            'mobilenumber': 'mobile_number',
            'accountId': 'account_id',
            'sms_id': 'incoming_id',
            'shortCode': 'sender_id',
            'mms_urls': 'mms_url',
            'channel_type': 'channel_type'
        }
        return map_keys(self.message, key_map)

    def _get_payload_for_auto_reply(self):
        log.info('Inside function _get_payload_for_autoreply')
        response = dict(messageid=self.message.get("sms_id"))
        sub_payload = self._get_payload_for_subscription()
        response.update(sub_payload)
        log.info(f"Final payload: {insensitive_data(response)}")
        return response

    def _get_payload_for_salesforce(self):
        log.info('Inside function _get_payload_for_salesforce')
        # key_from_message: required_key_for_worker_payload
        key_map = {
            'message': 'sms_text',
            'mobilenumber': 'mobile_number',
            'shortCode': 'inbound_number',
            'accountId': 'account_id',
            'sms_id': 'incoming_id',
            'mms_urls': 'mms_url',
            'providerName': 'providerName',
            'created_on': 'created_on',
            'bot_status': 'bot_status'
        }
        if 'channel_type' in self.message:
            key_map.update(channel_type='channel_type')
        if 'event_type' in self.message:
            key_map.update(event_type='event_type')
        return map_keys(self.message, key_map)

    def _get_payload_for_zoho(self):
        log.info('Inside function _get_payload_for_zoho')
        # key_from_message: required_key_for_worker_payload
        key_map = {
            'message': 'sms_text',
            'mobilenumber': 'mobile_number',
            'shortCode': 'inbound_number',
            'accountId': 'account_id',
            'sms_id': 'sms_id',
            'mms_urls': 'mms_url'
        }

        payload = map_keys(self.message, key_map)
        payload['type'] = 'incoming'
        payload['direction'] = 'IN'
        payload[CELERY_X_HEADER] = current_task.request.get(CELERY_X_HEADER)
        payload = generate_payload_for_crm(
            payload=payload,
            channel='mms' if self.message.get('mms_urls') else 'sms',
            crm='zoho',
            direction='in'
        )
        return payload

    def _get_payload_for_bullhorn(self):
        log.info("Inside function _get_payload_for_bullhorn")
        key_map = {
            'sms_id': 'id',
            'message': 'text',
            'mms_urls': 'mms_url'
        }
        payload = map_keys(self.message, key_map)
        return {
            'direction': 'incoming',
            'type': 'mms' if payload.get('mms_url') else 'sms',
            'messages': [payload]
        }

    @function_logger(log)
    def _get_payload_for_livechat(self):
        log.info('Inside function _get_payload_for_livechat')
        # key_from_message: required_key_for_worker_payload
        key_map = {'sms_id': 'message_id'}
        return map_keys(self.message, key_map)

    def _get_payload_for_url_from_account_config(self):
        log.info('Inside function _get_payload_for_url_from_account_config')
        params = {
            'id': self.message['sms_id'],
            'msg': self.message['message'],
            'sent_from': self.message['mobilenumber'],
            'sent_to': self.message['shortCode']
        }
        if self.message.get('mms_urls'):
            params['mms_urls'] = self.message['mms_urls']
        timestamp = self.message.get('created_on')
        timestamp = int(mktime(strptime(timestamp, '%Y-%m-%d %H:%M:%S')))
        params['timestamp'] = timestamp
        url = db_model.get_account_setting(self.account_id, 'push_incoming_url')
        method = db_model.get_account_setting(self.account_id,
                                              'push_incoming_url_type')
        return {
            'params': json.dumps(params),
            'url': url or '',
            'request_type': method or 'POST'
        }

    def _get_payload_for_url_from_incoming_config(self):
        log.info('Inside function _get_payload_for_url_from_incoming_config')
        params = {'id': self.message['sms_id']}
        message_field_name = self.account_config.get(
            'message_field_name') or 'msg'
        try:
            params[message_field_name] = self.message['message'].decode('utf-8')
        except Exception as e:
            log.error(f'in _get_payload_for_url_from_incoming_config: {e}')
            params[message_field_name] = self.message['message']
        mobile_field_name = self.account_config.get(
            'mobile_field_name') or 'sent_from'
        params[mobile_field_name] = self.message['mobilenumber']
        mobile_field_name = self.account_config.get(
            'shortcode_field_name') or 'sent_to'
        params[mobile_field_name] = self.message['shortCode']
        if self.message.get('mms_urls'):
            params['mms_urls'] = self.message['mms_urls']
        timestamp = self.message.get('created_on')
        timestamp = int(mktime(strptime(timestamp, '%Y-%m-%dT%H:%M:%S')))
        params['timestamp'] = timestamp
        return {
            'params': json.dumps(params),
            'url': self.account_config.get('push_url', ''),
            'request_type': self.account_config.get('http_method', 'POST')
        }

    def _get_payload_for_email(self):
        log.info('Inside function _get_payload_for_email')
        account_info = db_model.get_account_info(self.account_id)
        # key_from_message: required_key_for_worker_payload
        key_map = {
            'message': 'text',
            'mobilenumber': 'mobilenumber',
            'shortCode': 'shortcode',
            'mms_urls': 'mms_urls'
        }
        email_content = map_keys(self.message, key_map)
        email_content['name'] = account_info['contact_name']
        email_content = json.dumps(email_content)
        subject = 'SMS-Magic: Incoming text message {account_id}'.format(
            account_id=self.account_id)

        # Save the email in DB
        email = db_model.save_email(
            from_address=EMAIL_FROM_ADDRESS,
            to_address=account_info['email_id'],
            cc=CC_ADDRESS,
            subject=subject,
            template_type=PUSH_EMAIL_TEMPLATE_TYPE,
            variable_field_values=email_content)

        return {'system_email_log_id': email['id']}

    def _get_payload_for_bot(self):
        log.info('Inside function _get_payload_for_bot')
        # key_from_message: required_key_for_worker_payload
        key_map = {
            'sms_id': 'sms_id',
            'message': 'sms_text',
            'mobilenumber': 'phone_number',
            'shortCode': 'short_code',
            'accountId': 'account_id'
        }
        return map_keys(self.message, key_map)

    def _get_payload_for_subscription(self):
        log.info('Inside function _get_payload_for_subscription')
        # key_from_message: required_key_for_worker_payload
        key_map = {
            'message': 'message',
            'mobilenumber': 'mobile_number',
            'shortCode': 'sender_id',
            'accountId': 'account_id',
            'keyword': 'keyword',
            'subKeyword': 'sub_keyword'
        }
        return map_keys(self.message, key_map)

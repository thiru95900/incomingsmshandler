import re
from datetime import datetime

from sm_utils.utils import function_logger

from src.models.account import get_account
from src.models.database import db_model
from src.utils.config_loggers import log, log_json
from src.utils.constants import DUPLICATE_INCOMING_REDIS_EXPIRY, \
    CELERY_TASK_STATUS_FAILED, CELERY_TASK_STATUS_COMPLETED, \
    CELERY_TASK_STATUS_STARTED
from src.utils.redis_cache import redis_cache


@function_logger(log)
def is_account_hipaa_enabled(account_id):
    is_hipaa = db_model.get_account_tag(account_id, 'hipaa_compliant')
    log.info(f'The hipaa check for acc. {account_id} is : {is_hipaa}')
    log_json.info(f'the hipaa check for acc. {account_id} is : {is_hipaa}')
    return is_hipaa


@function_logger(log)
def get_inbound_number(shortcode, provider_id, table_source):
    inbound_number = db_model.get_inbound_number_by_shortcode(shortcode,
                                                              table_source)
    if not inbound_number:
        log.error(f"Inbound number not found for short-code: {shortcode}")
        log_json.error(f"Unable to process request as inbound number not found "
                       f"for shortcode:{shortcode}.")
        raise ValueError("INBOUND-NUMBER-NOT_FOUND")

    # Don't validate for correct provider for now, because multiple
    # entries for same providers exist on production server.
    if inbound_number["incoming_provider_id"] != provider_id:
        log.warning(f"Inbound number {inbound_number} is not associated with "
                    f"provider {provider_id}")
        # raise ValueError("INVALID-INBOUND-NUMBER-FOR-PROVIDER")

    return inbound_number


@function_logger(log)
def get_incoming_config(shortcode, keyword=None):
    incoming_config = db_model.get_incoming_config_by_shortcode(shortcode,
                                                                keyword=keyword)
    if incoming_config:
        account_id = incoming_config.get('account_id')
        validate_account_id(account_id)
    else:
        log.error(f'Incoming config not found for shortcode: {shortcode}')
        log_json.error(f'Incoming config not found for shortcode: {shortcode}')
        raise ValueError("INCOMING-CONFIG-NOT_FOUND")

    log.debug(f"Account info for shortcode {shortcode}: {incoming_config}")
    log_json.info(f"account_id = {account_id} for shortcode: {shortcode}.",
                  extra={'account_id': account_id})
    is_bullhorn_account = db_model.is_bullhorn_account(account_id)
    incoming_config['push_to_bullhorn'] = is_bullhorn_account
    return incoming_config


@function_logger(log)
def is_shared_number(inbound_number_info):
    is_shared = bool(inbound_number_info.get("is_shared"))
    log.debug(f"{inbound_number_info} is_shared = {is_shared}")
    return is_shared


@function_logger(log)
def get_keywords(message):
    keyword, sub_keyword = None, None
    # Remove extra spaces from the message
    message = re.sub('\\s+', ' ', message)
    message_split = message.split(" ")
    keyword = message_split[0]
    if len(message_split) > 1:
        sub_keyword = message_split[1]
    log.debug(f"Keywords in message are: {keyword}, {sub_keyword}")
    return keyword, sub_keyword


@function_logger(log)
def validate_account_id(account_id):
    if not account_id:
        log.exception('Error while validating account id. It is not set')
        log_json.error(f'Failed to validate account_id: {account_id}')
        raise ValueError("ACCOUNT-NOT-VALID")
    account = get_account(account_id=int(account_id))
    if not account:
        log.error(f"Account not found for account id: {account_id}")
        log_json.error(f"Unable to process request as Valid Account not found "
                       f"for account_id:{account_id}")
        raise ValueError("ACCOUNT-NOT-FOUND")


@function_logger(log)
def save_mms_urls(is_hipaa, params, sms_id):
    urls = params.get("mms_urls", [])
    skip = params.get("skip_db_url_storage")
    if not urls:
        return

    if not isinstance(urls, list):
        urls = [urls]

    for url in urls:
        db_model.save_mms_url(is_hipaa, url, sms_id, skip)


def save_incoming_sms(params):
    log.info('Inside function save_incoming_sms')
    params["incomingProviderId"] = params["providerId"]
    account_id = params.get('accountId')
    is_hipaa = is_account_hipaa_enabled(account_id)
    sms_record = db_model.save_incoming_sms(is_hipaa, params)
    if params.get("mms_urls", []) and not params.get("skip_db_url_storage"):
        save_mms_urls(is_hipaa, params, sms_record["id"])
    return sms_record


def save_incoming_message_part(params):
    log.info('Inside function save_incoming_message_part')
    return db_model.save_incoming_sms_part(params)


def get_count_of_parts(params):
    log.debug('Inside function get_count_of_parts function')
    return db_model.get_count_of_parts(
        params.get("referenceId"),
        params.get("shortCode"),
        params.get("accountId"),
        params.get("mobilenumber")
    )


def are_all_parts_received(params, count_of_stored_parts):
    log.info('Inside function are_all_parts_received function')
    return count_of_stored_parts >= params.get("totalParts")


def assemble_message(params):
    log.info('Inside function assemble_message')
    parts = db_model.get_parts_of_sms(
        params.get("referenceId"),
        params.get("shortCode"),
        params.get("accountId"),
        params.get("mobilenumber")
    )
    if not parts:
        log.debug("No message parts")
        return

    message = ''
    for p in parts:
        try:
            message += p['message']
        except UnicodeEncodeError:
            try:
                message += p['message'].decode("utf-8")
            except Exception as e:
                log.exception(f'Error while joining message parts: {e}')
    try:
        message = message.encode("utf-8")
    except Exception as e:
        log.exception(f'Error while encoding message: {e}')

    return message


def update_parts_of_message_after_assembly(params):
    log.info('Inside function update_parts_of_message_after_assembly')
    db_model.update_parts_of_sms(
        params["referenceId"],
        params["shortCode"],
        params["accountId"],
        params["mobilenumber"],
        params["sms_id"]
    )


@function_logger(log)
def get_apikey(account_id):
    return db_model.get_apikey_by_account_id(account_id)


@function_logger(log)
def get_duplicate_expiry(account_id):
    expiry_in_sec = db_model.get_account_setting(
        account_id, DUPLICATE_INCOMING_REDIS_EXPIRY) or 0
    log.info(f'Setting - {DUPLICATE_INCOMING_REDIS_EXPIRY}: {expiry_in_sec}')
    return expiry_in_sec


@function_logger(log)
def update_duplicate_incoming_expiry(account_id, duplicate_key):
    duplicate_expiry = get_duplicate_expiry(account_id)
    if not duplicate_expiry:
        return

    try:
        redis_cache.expire(duplicate_key, duplicate_expiry)
        ttl = redis_cache.ttl(duplicate_key)
        log.info(f'Remaining TTL of key {duplicate_key}: {ttl}')
        log_json.debug(f'Remaining TTL of key {duplicate_key}: {ttl}')
    except Exception as e:
        log.exception(f'Error:update_duplicate_incoming_expiry: {e}')
        log_json.exception('Exception occurred while checking Expiry time for '
                           'duplicate Incoming message key in Redis',
                           extra={'error': str(e),
                                  'duplicate_incoming_redis_key':
                                      duplicate_key})


@function_logger(log)
def check_multichannel(channel_type):
    return db_model.check_multichannel(channel_type=channel_type)


@function_logger(log)
def get_storage_setting(account_id):
    return db_model.get_account_setting(account_id, "incomingStorage")


def start_celery_task(entry_id=None):
    return db_model.update_celery_task(
        entry_id=entry_id, status=CELERY_TASK_STATUS_STARTED)


def complete_celery_task(entry_id=None):
    return db_model.update_celery_task(
        entry_id=entry_id, status=CELERY_TASK_STATUS_COMPLETED)


def fail_celery_task(entry_id=None, error=None):
    return db_model.update_celery_task(
        entry_id=entry_id, status=CELERY_TASK_STATUS_FAILED, error=error)

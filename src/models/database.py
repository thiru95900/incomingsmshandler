import datetime
import time

from celery import current_task
from retrying import retry
from sm_models.account import IncomingConfig
from sm_models.inbound_numbers import ChannelType
from sm_models.incoming import IncomingSms, IncomingSmsParts, \
    IncomingSMSSyncAudit, IncomingMmsMediaUrl
from sm_models.providers import WhatsappAccountMobileMapping
from sm_models.task_loggers import SystemEmailLog, CeleryTask
from sm_utils.utils import function_logger
from sqlalchemy import func

from src import config
from src.models.account import get_account_tags, get_account_settings, \
    get_apikey, get_account, is_bullhorn
from src.utils.config_loggers import log
from src.utils.constants import CELERY_TASK_STATUS_STARTED, \
    CELERY_TASK_STATUS_COMPLETED, CHANNEL
from src.utils.database import session
from src.utils.helper import get_orm_column_mapping, to_dict, random_sleep, \
    insensitive_data
from src.utils.redis_cache import magic_cache, redis_cache


class Model(object):

    @staticmethod
    def rollback_session():
        try:
            session.rollback()
            log.warning('Session rolled back successfully')
        except Exception as e:
            log.exception(f'Error while rolling back the db session: {e}')

    @staticmethod
    def get_apikey_by_account_id(account_id):
        return get_apikey(account_id=account_id)

    @staticmethod
    def get_inbound_number_by_shortcode(short_code, table_source):
        sql = session.query(table_source)
        sql = sql.filter(table_source.short_code == short_code)
        sql = sql.filter(table_source.is_deleted == 0)
        number = sql.first()
        return to_dict(number)

    @staticmethod
    def get_incoming_config_by_shortcode(short_code, keyword=None):
        sql = session.query(IncomingConfig)
        sql = sql.filter(IncomingConfig.short_code == short_code)
        sql = sql.filter(IncomingConfig.is_deleted == 0)
        if keyword:
            sql = sql.filter(IncomingConfig.keyword == keyword)
        incoming_config = sql.first()
        return to_dict(incoming_config)

    @staticmethod
    def check_multichannel(channel_type=None):
        if channel_type:
            sql = session.query(ChannelType.is_multichannel)
            sql = sql.filter(ChannelType.name == channel_type)
            sql = sql.filter(ChannelType.is_deleted == 0)
            return sql.first()
        return 0

    @staticmethod
    def get_keyword_whatsapp_mapping(short_code, mobile_number):
        sql = session.query(WhatsappAccountMobileMapping)
        sql = sql.filter_by(shortCode=short_code, mobileNumber=mobile_number)
        sql = sql.order_by(WhatsappAccountMobileMapping.createdOn.desc())
        result = sql.first()
        return (result.keyword, result.subKeyword) if result else (None, None)

    @staticmethod
    def insert_keyword_whatsapp_mapping(**params):
        record = WhatsappAccountMobileMapping(**params)
        session.add(record)
        session.commit()

    @staticmethod
    def save_mms_url(is_hipaa, url, sms_id, skip_url_storage=None):
        created_on = time.strftime("%Y-%m-%d %H:%M:%S")
        if is_hipaa:
            url = '<< mms url is not stored due to hipaa compliance >>'
        elif skip_url_storage:
            url = '<< opted for salesforce storage >>'

        mms_params = {
            'url': url,
            'incoming_sms_id': sms_id,
            'created_on': created_on
        }
        mms_url = IncomingMmsMediaUrl(**mms_params)
        session.add(mms_url)
        session.flush()
        return to_dict(mms_url)

    @staticmethod
    @function_logger(log)
    def save_incoming_sms(is_hipaa, params):
        mapping = get_orm_column_mapping(IncomingSms)
        params = {v: params[k] for k, v in mapping.items() if k in params}
        template = '<< {} is not stored due to hipaa compliance >>'
        if is_hipaa and params.get('message'):
            params['message'] = template.format('text')

        if is_hipaa and params.get('media_url'):
            params['media_url'] = template.format('mms url')

        if params.get('mms_urls') and params.get('channel_type') == CHANNEL.SMS:
            params['channel_type'] = CHANNEL.MMS

        log.info(f'Incoming SMS parameters: {insensitive_data(params)}')
        params.update({
            'created_on': datetime.datetime.now(datetime.timezone.utc),
            'modified_on': datetime.datetime.now(datetime.timezone.utc)
        })
        sms = IncomingSms(**params)
        session.add(sms)
        session.commit()
        return to_dict(sms)

    @staticmethod
    def save_incoming_sms_part(params):
        mapping = get_orm_column_mapping(IncomingSmsParts)
        params = {v: params[k] for k, v in mapping.items() if k in params}
        if "incoming_sms_id" not in params:
            params["incoming_sms_id"] = 0

        if 'part_number' not in params:
            params["part_number"] = 1

        part = IncomingSmsParts(**params)
        session.add(part)
        session.commit()
        log.info(f'Saved message part id: {part.id}')
        return part.id

    @staticmethod
    def get_count_of_parts(reference_id, short_code, account_id, mobile_number):
        # Sleep for random milliseconds between 100 and 500. This is to deal
        # with parts which comes at the same time and processed by different
        # thread/processes
        random_sleep()
        parts_key = Model.get_part_key(
            account_id,
            short_code,
            mobile_number,
            reference_id
        )
        count_of_parts = redis_cache.incr(parts_key)
        # Check if Redis returning correct data
        if not count_of_parts:
            log.error('Error while fetching parts count from Redis. '
                      'Now fetching from database')
            return Model.get_parts_count_from_db(
                reference_id,
                short_code,
                account_id,
                mobile_number
            )
        # The key should be expired within 24 hours to keep Redis memory in
        # check so set expiry on when key is created in Redis first time.
        # Although, key is deleted when message parts get assembled but this is
        # fallback
        if count_of_parts == 1:
            redis_cache.expire(parts_key, 3600 * 24)

        return count_of_parts

    @staticmethod
    def get_parts_count_from_db(reference_id, short_code, account_id,
                                mobile_number):
        sql = session.query(func.count(IncomingSmsParts.id))
        cached_id = Model.get_part_cached_id()
        if cached_id:
            sql = sql.filter(IncomingSmsParts.id >= cached_id)
        sql = sql.filter(IncomingSmsParts.account_id == account_id)
        sql = sql.filter(IncomingSmsParts.reference_id == reference_id)
        sql = sql.filter(IncomingSmsParts.incoming_sms_id == 0)
        sql = sql.filter(IncomingSmsParts.short_code == short_code)
        sql = sql.filter(IncomingSmsParts.mobile_number == mobile_number)
        return sql.scalar()

    @staticmethod
    def get_parts_of_sms(reference_id, short_code, account_id, mobile_number):
        # Sleep for random milliseconds between 100 and 500. This is to deal
        # with parts which comes at the same time and processed by different
        # thread/processes
        random_sleep()
        sql = session.query(IncomingSmsParts)
        cached_id = Model.get_part_cached_id()
        if cached_id:
            sql = sql.filter(IncomingSmsParts.id >= cached_id)
        sql = sql.filter(IncomingSmsParts.account_id == account_id)
        sql = sql.filter(IncomingSmsParts.reference_id == reference_id)
        sql = sql.filter(IncomingSmsParts.incoming_sms_id == 0)
        sql = sql.filter(IncomingSmsParts.short_code == short_code)
        sql = sql.filter(IncomingSmsParts.mobile_number == mobile_number)
        sql = sql.order_by(IncomingSmsParts.part_number)
        parts = sql.all()
        return to_dict(parts)

    @staticmethod
    @retry(wait_fixed=1000, stop_max_attempt_number=3)
    def update_parts_of_sms(reference_id, short_code, account_id, mobile_number,
                            sms_id):
        log.info(f'Inside function update_parts_of_sms: {locals()}')
        try:
            sql = session.query(IncomingSmsParts)
            cached_id = Model.get_part_cached_id()
            if cached_id:
                sql = sql.filter(IncomingSmsParts.id >= cached_id)
            parts = sql.filter(
                IncomingSmsParts.account_id == account_id,
                IncomingSmsParts.reference_id == reference_id,
                IncomingSmsParts.incoming_sms_id == 0,
                IncomingSmsParts.short_code == short_code,
                IncomingSmsParts.mobile_number == mobile_number
            ).all()
            for part in parts:
                part.incoming_sms_id = sms_id
                part.status = "success"
                part.modified_on = datetime.datetime.now(datetime.timezone.utc)
            session.flush()
            # Delete parts counting key as all parts are already assembled.
            redis_cache.delete(Model.get_part_key(
                account_id,
                short_code,
                mobile_number,
                reference_id
            ))
            log.info('Updated table incoming_sms_parts successfully')
        except Exception as e:
            log.warning(f'Error while updating incoming_sms_parts: {e}')
            db_model.rollback_session()
            raise e

    @staticmethod
    def audit_sync(account_id, incoming_sms_id, sync_type):
        audit_params = {
            'account_id': account_id,
            'incoming_sms_id': incoming_sms_id,
            'sync_type': sync_type
        }
        activity = IncomingSMSSyncAudit(**audit_params)
        session.add(activity)
        session.flush()

    @staticmethod
    def get_account_info(account_id):
        return get_account(account_id=account_id)

    @staticmethod
    def save_email(**kwargs):
        email = SystemEmailLog(**kwargs)
        session.add(email)
        session.commit()
        return to_dict(email)

    @staticmethod
    def get_account_tag(account_id, tag_name):
        all_tags = get_account_tags(account_id=account_id)
        return bool(all_tags.get(tag_name))

    @staticmethod
    def get_account_setting(account_id, setting):
        all_settings = get_account_settings(account_id=account_id)
        return all_settings.get(setting)

    @staticmethod
    @retry(wait_fixed=1000, stop_max_attempt_number=3)
    def update_celery_task(entry_id=None, status=None, error=None):
        log.info(f'Inside function update_celery_task: {locals()}')
        if not entry_id:
            return None
        try:
            sql = session.query(CeleryTask).filter_by(entry_id=entry_id)
            c_task = sql.first()
            c_task.task_status = status

            if status == CELERY_TASK_STATUS_STARTED:
                c_task.started_on = datetime.datetime.now(datetime.timezone.utc)
                session.commit()
                log.info(f'Celery Tasks {entry_id} updated: status = {status}')
                return True

            c_task.finished_on = datetime.datetime.now(datetime.timezone.utc)
            c_task.error_message = error or None
            account_id = current_task.request.kwargs.get('account_id')
            if account_id:
                c_task.account_id = account_id
                hipaa_flag = 'hipaa_compliant'
                is_hipaa = db_model.get_account_tag(account_id, hipaa_flag)
                if is_hipaa and status == CELERY_TASK_STATUS_COMPLETED:
                    c_task.payload_data = '<< payload removed due to hipaa >>'
            session.commit()
            log.info(f'Celery Tasks {entry_id} updated: status = {status}')
            return True
        except Exception as e:
            log.warning(f'Error while updating celery tasks: {entry_id} - {e}')
            db_model.rollback_session()
            raise e

    @staticmethod
    def update_celery_task_id(is_hipaa, entry_id, task_id):
        session.commit()
        c_task = session.query(CeleryTask).filter_by(entry_id=entry_id).first()
        c_task.task_id = task_id
        if is_hipaa:
            c_task.payload_data = '<< payload removed due to hipaa >>'
        session.flush()

    @staticmethod
    def is_bullhorn_account(account_id):
        return is_bullhorn(account_id=account_id)

    @staticmethod
    @magic_cache(expiry=3600 * 24)
    def get_part_cached_id():
        """
        This method caches incoming_sms_parts table id from 24 hours ago. This
        id will be used in incoming_sms_parts search queries for faster
        retrieval. The assumption here is that all parts of messages should come
        within 24 hours.
        """
        result = session.execute(config.INTERVAL_QUERY)
        record = result.first() if result.rowcount > 0 else None
        if not record:
            log.error('CAN_NOT_OBTAINED_INCOMING_SMS_PARTS_ID')
            return None
        return record.id

    @staticmethod
    def get_part_key(account_id, short_code, mobile_number, reference_id):
        """
        This will generate unique key for group of message parts. We will use
        this key to store parts count into Redis
        """
        part_key = f'{config.APP_NAME}:{account_id}:{short_code}:' \
                   f'{mobile_number}:{reference_id}'
        log.info(f'Function get_part_key return: {part_key}')
        return part_key


db_model = Model()

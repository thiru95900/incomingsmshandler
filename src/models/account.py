from sm_models.account import AccountTag, Account, AccountFlag, \
    AccountRelationship, AccountSetting
from sm_models.auth_info import AuthInfo
from sm_models.salesforce import SalesforceAuthCodeMap
from sm_utils.utils import not_empty, function_logger

from src.utils.config_loggers import log, log_json
from src.utils.constants import IS_PUSH_ENABLED_ACCOUNT_TAG_FLAG_NAME, \
    IS_CONVERSE_DESK_ENABLED_ACCOUNT_TAG_FLAG_NAME, ACTIVE
from src.utils.database import session
from src.utils.helper import to_dict
from src.utils.redis_cache import magic_cache


@magic_cache(expiry=3600, kwargs_key=['account_id'])
def get_account_tags(account_id=None):
    sql = session.query(AccountTag)
    sql = sql.filter(AccountTag.account_id == account_id)
    all_tags = sql.all()
    return {tag.flag_name: tag.flag_value for tag in all_tags}


@magic_cache(expiry=3600, kwargs_key=['account_id'])
def get_account_settings(account_id=None):
    sql = session.query(AccountSetting)
    sql = sql.filter(AccountSetting.account_id == account_id)
    all_settings = sql.all()
    return {item.setting_name: item.setting_value for item in all_settings}


@magic_cache(expiry=3600, kwargs_key=['account_id'])
def get_account_flags(account_id=None):
    sql = session.query(AccountFlag)
    sql = sql.filter(AccountFlag.account_id == account_id)
    account_flags = sql.order_by(AccountFlag.modified_on.desc()).all()
    return to_dict(account_flags, single=True)


@magic_cache(expiry=3600, kwargs_key=['account_id'])
def get_account(account_id=None):
    sql = session.query(Account)
    return to_dict(sql.filter(Account.id == account_id).first())


@function_logger(log)
def get_apikey(account_id=None):
    return get_account(account_id=account_id).get('api_key')


@function_logger(log)
def is_push_enabled_account(account_id=None):
    all_tags = get_account_tags(account_id=account_id)
    return all_tags.get(IS_PUSH_ENABLED_ACCOUNT_TAG_FLAG_NAME, None)


@function_logger(log)
def is_saas_converse_desk_enabled(account_id=None):
    all_tags = get_account_tags(account_id=account_id)
    return all_tags.get(IS_CONVERSE_DESK_ENABLED_ACCOUNT_TAG_FLAG_NAME, 0)


@function_logger(log)
def get_sf_auth_map(account_id=None):
    sql = session.query(SalesforceAuthCodeMap)
    sql = sql.filter_by(account_id=account_id)
    sql = sql.order_by(SalesforceAuthCodeMap.modified_on.desc(),
                       SalesforceAuthCodeMap.id.desc())
    return sql.first()


@function_logger(log)
def get_parent_of_account(account_id=None):
    sql = session.query(AccountRelationship)
    sql = sql.filter(AccountRelationship.account_id == account_id)
    sql = sql.filter(AccountRelationship.is_deleted == 0)
    account_relations = sql.first()
    return account_relations.parent_account_id if account_relations else 0


@function_logger(log)
@not_empty('account_id', 'REQ_ACCOUNT_ID_MISSING', var_type=int, req=True)
def get_account_id_or_parent_id(**kwargs):
    account_id = kwargs.get('account_id')
    is_oauth_enabled = False
    account_flags = get_account_flags(**kwargs)
    is_oauth_package = account_flags.get('is_oauth_package')
    if is_oauth_package:
        sf_auth_map = get_sf_auth_map(account_id=account_id)
        is_oauth_enabled = bool(sf_auth_map)

    parent_account_id = 0
    if is_oauth_enabled:
        log.info(f'OAuth is enabled for {account_id}, no need to fetch parent')
    else:
        log.info(f'OAuth is not set for account {account_id}, fetch parent')
        parent_account_id = get_parent_of_account(account_id=account_id)
        log.info(f'Parent of account {account_id} is {parent_account_id}')

    return parent_account_id or account_id


@magic_cache(expiry=3600 * 24, kwargs_key=['account_id'])
def is_bullhorn(account_id=None):
    sql = session.query(AuthInfo)
    sql = sql.filter(AuthInfo.account_id == account_id)
    sql = sql.filter(AuthInfo.is_deleted == ACTIVE)
    bullhorn_auth_info = sql.first()

    if bullhorn_auth_info:
        log.info(f'An account found associated with Bullhorn CRM: {account_id}')
        log_json.info('This account is associated with Bullhorn CRM.')
        return True
    return False

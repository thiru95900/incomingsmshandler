from sm_models.account import AccountRelationship, Account
from sm_models.country import CountryInfo
from sm_models.customer_billing import MultichannelMeteringMap, \
    CustomerSubscriptions, CustomerAccountBalance
from sm_models.customers import Customers
from sm_models.providers import ServiceProvider, IncomingProvider
from sm_utils.utils import function_logger

from src.models.account import get_account_tags
from src.utils.config_loggers import log
from src.utils.database import session

DEFAULT_FALSE_FLAG, DEFAULT_TRUE_FLAG = 1, 0
CHILD_ACCOUNT_FLAG = 2
CUSTOMER_THRESHOLD_BAL_AMT = 0


@function_logger(log)
def get_metering_type(channel_type, message_type):
    sql = session.query(MultichannelMeteringMap.metering_type)
    sql = sql.filter_by(channel_type=channel_type, message_type=message_type)
    record = sql.first()
    return record.metering_type if record else None


@function_logger(log)
def is_core_subscribed(customer_id):
    sql = session.query(CustomerSubscriptions.is_core)
    sql = sql.filter_by(customer_id=customer_id, is_deleted=DEFAULT_TRUE_FLAG)
    result = sql.first()
    return bool(result.is_core) if result else False


@function_logger(log)
def get_customer_details(account_id):
    # Get parent accountId for child account
    sql = session.query(AccountRelationship.parent_account_id)
    sql = sql.filter(AccountRelationship.is_deleted == DEFAULT_FALSE_FLAG)
    sql = sql.filter(AccountRelationship.is_master == CHILD_ACCOUNT_FLAG)
    sql = sql.filter(AccountRelationship.account_id == account_id)
    account_relationship = sql.first()

    if account_relationship:
        account_id = account_relationship.parent_account_id

    sql = session.query(Customers.id, Customers.billing_external_eid)
    sql = sql.join(Account, Account.customer_id == Customers.id)
    sql = sql.filter(Account.id == account_id)
    sql = sql.filter(Customers.is_deleted == DEFAULT_TRUE_FLAG)
    customer_object = sql.first()
    if customer_object:
        customer_id = customer_object.id
        billing_external_eid = customer_object.billing_external_eid
    else:
        customer_id = None,
        billing_external_eid = None

    return {
        'account_id': account_id,
        'customer_id': customer_id,
        'billing_external_eid': billing_external_eid
    }


@function_logger(log)
def get_customer_and_is_core_details(account_id):
    log.info('master switch for billing metering is True')
    all_tags = get_account_tags(account_id=account_id)
    usage_enabled = bool(all_tags.get('billing_usage_enabled'))
    log.info(f'account tags setting for usage_enabled is {usage_enabled}')
    customer_details = get_customer_details(account_id)
    customer_id = customer_details.get("customer_id")
    billing_external_eid = customer_details.get("billing_external_eid")
    is_core = is_core_subscribed(customer_id)
    core_subscribed = bool(is_core and usage_enabled)
    log.info(f"core_subscribed flag for account :{account_id} with "
             f"customer_id :{customer_id} having "
             f"billing_eid:{billing_external_eid} is {core_subscribed}")
    return {
        'account_id': account_id,
        'customer_id': customer_id,
        'billing_external_eid': billing_external_eid,
        'core_subscribed': core_subscribed
    }


@function_logger(log)
def check_sufficient_balance_available(account_id):
    sufficient_balance = False
    billing_credit_bucket_id = None
    sql = session.query(CustomerAccountBalance)
    sql = sql.filter(CustomerAccountBalance.account_id == account_id)
    sql = sql.filter(CustomerAccountBalance.is_deleted == DEFAULT_TRUE_FLAG)
    customer_balance = sql.first()
    if customer_balance:
        billing_credit_bucket_id = customer_balance.billing_credit_bucket_id
        credits_allocated = customer_balance.credits_allocated
        credits_used = customer_balance.credits_used
        remaining_credits = credits_allocated - credits_used
        if remaining_credits > CUSTOMER_THRESHOLD_BAL_AMT:
            sufficient_balance = True

    return sufficient_balance, billing_credit_bucket_id


@function_logger(log)
def is_tpi(sender_id):
    sql = session.query(ServiceProvider)
    sql = sql.filter_by(route_tag=sender_id, is_tpi=1, is_deleted=0)
    return bool(sql.first())


@function_logger(log)
def get_provider_name(provider_id):
    sql = session.query(IncomingProvider.name)
    sql = sql.filter_by(id=provider_id, is_deleted=0)
    provider = sql.first()
    return provider.name if provider else "noprovider"


@function_logger(log)
def get_sender_id_type(table, sender_id):
    sql = session.query(table.country_id, table.inbound_number_type)
    sql = sql.filter_by(short_code=sender_id, is_deleted=0)
    number = sql.first()
    return (number.country_id, number.inbound_number_type) if number else (0, 1)


@function_logger(log)
def get_country_name(country_id):
    sql = session.query(CountryInfo.country_name)
    sql = sql.filter_by(id=country_id, is_deleted=0)
    country = sql.first()
    return country.country_name if country else "nocountry"

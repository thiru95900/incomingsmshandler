import datetime
from functools import wraps
from random import randint
from time import sleep
from sqlalchemy import inspect

from src.utils.config_loggers import log
from src.utils.constants import MASK_FILTER


def to_dict(model=None, single=False):
    def _object_to_dict(obj):
        if obj:
            _columns = getattr(obj, '__mapper__').columns.keys()
            return {c: check_dates(getattr(obj, c)) for c in _columns}
        return {}

    if isinstance(model, list):
        _list = [_object_to_dict(r) for r in model]
        return {k: v for d in _list for k, v in d.items()} if single else _list
    return _object_to_dict(model)


def check_dates(date_object):
    if isinstance(date_object, (datetime.datetime, datetime.date)):
        return date_object.isoformat()
    return date_object


def get_orm_column_mapping(orm_class):
    mapper = inspect(orm_class)
    orm_keys = mapper.columns.keys()
    db_keys = [e.key for e in mapper.columns.values()]
    return dict(zip(db_keys, orm_keys))


def handle_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.error(f"Error in function {func.__name__}: {str(e)}")

    return wrapper


def insensitive_data(data_dict):
    return masked_data(data_dict, filter_words=['message', 'text']) \
        if isinstance(data_dict, dict) else data_dict


def masked_data(data=None, filter_words=MASK_FILTER):
    result = {}
    if data and isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = masked_data(v)
            elif isinstance(v, list):
                result[k] = list(map(masked_data, v))
            else:
                result[k] = '****' if k in filter_words else v
    else:
        result = data
    return result


def map_keys(dictionary, mapper):
    return {
        mapper[k]: byte_to_str(v) for k, v in dictionary.items() if k in mapper
    }


def byte_to_str(substring):
    return substring.decode('utf-8') if isinstance(substring, bytes) else \
        substring


def random_sleep():
    sleep(float(randint(100, 500)/1000))

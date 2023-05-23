import json
from functools import wraps

from src import config
from src.utils.config_loggers import log


def magic_cache(expiry=3600, args_key=None, kwargs_key=None):
    """
    Decorator for caching function return values into redis
    param: expiry - expiry of the key in seconds
    param: args_key - positional args keys [sequence must be maintained with
    the actual function arguments]
    param: kwargs_key - keyword args keys
    return: cached data if exists in redis or data from function return
    """

    def function_cache(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            log.debug(f'magic cache - args: {args}, kwargs: {kwargs}')
            cache_key = f'{config.APP_NAME}:{fn.__name__.upper()}'
            if args_key:
                for i, item in enumerate(args_key):
                    cache_key += f':{item}:{args[i]}'
            if kwargs_key:
                for key in kwargs_key:
                    cache_key += f':{key}:{kwargs.get(key, "STATIC")}'
            log.info(f'cache_key: {cache_key}')
            data_json = redis_cache.get(cache_key)
            if data_json:
                log.info(f'Fetching {cache_key} from cache')
                response = json.loads(data_json)
                log.info(f'Response: Redis cache: {response}')
                return response

            log.info('Getting data from function')
            response = fn(*args, **kwargs)
            log.info(f'Response from function: {response}')
            if response is not None and cache_key:
                data_json = json.dumps(response)
                redis_cache.set(cache_key, data_json, expiry)
            return response

        return wrapper

    return function_cache


class RedisCache:

    def __init__(self, redis_client):
        log.info('In the constructor of RedisCache')
        self.redis_client = redis_client

    def __getattr__(self, method_name):
        log.debug(f'RedisCache.__getattr__: {method_name}')
        try:
            redis_method = getattr(self.redis_client, method_name)
        except Exception as e:
            log.error(f'RedisCache:Prop:Exception:{method_name}: {e}')
            return RedisCache._stub
        return self._wrapper(redis_method)

    @staticmethod
    def _wrapper(f):
        def applicator(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as err:
                log.error(f'RedisCache:Exception:{f.__name__}: {err}')
            return None

        return applicator

    @staticmethod
    def _stub(*args, **kwargs):
        log.debug(f'In RedisCache.stub: args: {args}, kwargs: {kwargs}')
        return None


def get_redis_client():
    redis_client = None
    try:
        if config.SERVICE_REDIS_CLUSTER_HOST in ('localhost', '127.0.0.1'):
            from redis import Redis
            redis_client = Redis(decode_responses=True, socket_timeout=10)
        else:
            from rediscluster import RedisCluster
            redis_client = RedisCluster(
                host=config.SERVICE_REDIS_CLUSTER_HOST,
                port=int(config.SERVICE_REDIS_CLUSTER_PORT),
                decode_responses=True,
                socket_timeout=10
            )
    except Exception as e:
        log.exception(f'Exception in redis connection {e}')

    return RedisCache(redis_client)


redis_cache = get_redis_client()

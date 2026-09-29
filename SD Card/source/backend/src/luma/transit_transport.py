"""One quota-accounted HTTPS transport shared by all 511 transit requests."""
import json
import logging
import math
import re
from datetime import UTC, datetime
from time import time

import httpx


class TransitUnavailable(ValueError):
    pass


class TransitQuota(TransitUnavailable):
    pass


class TransitLogFilter(logging.Filter):
    def filter(self, record):
        message=record.getMessage()
        if 'api.511.org' in message:
            record.msg=re.sub(r'(api_key=)[^&\s\"\']+',r'\1[redacted]',message,flags=re.I)
            record.args=()
        return True


# httpx's INFO request line contains query strings. Never log the owner's token.
logging.getLogger('httpx').addFilter(TransitLogFilter())


class TransitBudget:
    """Atomically reserve before I/O; failures count, restart never resets quota."""
    LIMIT=55

    def __init__(self,storage,clock=time):
        self.storage,self.clock=storage,clock

    def reserve(self):
        now=self.clock()
        if not math.isfinite(now):raise TransitQuota('Transit clock unavailable.')
        with self.storage.transaction() as connection:
            row=connection.execute("SELECT payload FROM cache WHERE namespace='transit' AND key='budget'").fetchone()
            try:
                history=json.loads(row['payload']) if row else []
                if (not isinstance(history,list) or len(history)>self.LIMIT
                        or any(type(t) not in (int,float) or not math.isfinite(t) for t in history)):
                    raise ValueError()
            except (ValueError,TypeError):raise TransitQuota('Transit request history needs recovery.') from None
            # Retain future timestamps after a clock rollback: fail closed, never refill.
            recent=[t for t in history if t>now-3600]
            if any(t>now for t in recent):raise TransitQuota('Transit is waiting for clock synchronization.')
            if len(recent)>=self.LIMIT:raise TransitQuota('Transit hourly request allowance reached. Saved data retained.')
            recent.append(now)
            connection.execute("""INSERT INTO cache(namespace,key,payload,updated_at) VALUES('transit','budget',?,?)
                ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
                (json.dumps(recent),datetime.fromtimestamp(now,UTC).isoformat()))


class TransitTransport:
    ENDPOINTS={'operators','lines','stops','StopMonitoring','stoptimetable'}
    MAX_BYTES=4*1024*1024

    def __init__(self,budget,token,*,transport=None):
        self.budget,self.token=budget,token
        self.client=httpx.Client(timeout=httpx.Timeout(10,connect=5),follow_redirects=False,
                                 trust_env=False,transport=transport)

    def close(self):self.client.close()

    def request(self,endpoint,**params):
        if endpoint not in self.ENDPOINTS:raise TransitUnavailable('Unknown transit endpoint.')
        if any(not isinstance(k,str) or not isinstance(v,(str,int)) for k,v in params.items()):
            raise TransitUnavailable('Invalid transit query.')
        if {'api_key','format'} & params.keys():raise TransitUnavailable('Reserved transit parameters.')
        token=self.token()
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',token):
            raise TransitUnavailable('Add a valid 511 token locally.')
        self.budget.reserve()
        try:
            with self.client.stream('GET',f'https://api.511.org/transit/{endpoint}',params={**params,'format':'json','api_key':token}) as response:
                if response.status_code in (401,403):raise TransitUnavailable('511 rejected the token. Check local transit setup.')
                if response.status_code==429:raise TransitQuota('511 rate limit reached. Wait before retrying.')
                if response.status_code!=200:raise TransitUnavailable('511 is unavailable. Saved data retained.')
                chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>self.MAX_BYTES:raise TransitUnavailable('Transit response exceeded the device limit.')
                    chunks.append(chunk)
                result=json.loads(b''.join(chunks).decode('utf-8-sig'))
                if not isinstance(result,(dict,list)):raise ValueError()
                return result
        except TransitUnavailable:raise
        except (httpx.HTTPError,ValueError,UnicodeError):
            # Neither provider error bodies nor exception URLs enter UI/log output.
            raise TransitUnavailable('Could not read transit data. Saved data retained.') from None

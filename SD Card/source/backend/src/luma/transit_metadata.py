"""Bounded discovery adapters for 511's documented JSON (not its XML shape)."""
import re

from .transit_parser import boolean, items, text
from .transit_transport import TransitUnavailable


def identifier(value):
    # Provider route IDs legitimately contain spaces, slash and colon.
    if not isinstance(value,str) or not 1<=len(value.strip())<=160 or re.search(r'[\x00-\x1f\x7f]',value):
        raise ValueError('Invalid transit identifier.')
    return value.strip()


def _id(row,*names):
    try:return identifier(next(row[name] for name in names if row.get(name)))
    except (ValueError,StopIteration):return None


def parse_metadata(kind,payload):
    if kind not in ('operators','lines','stops'):raise TransitUnavailable('Unknown transit directory.')
    if kind=='stops':
        contents=payload.get('Contents') if isinstance(payload,dict) else None
        objects=contents.get('dataObjects') if isinstance(contents,dict) else None
        records=objects.get('ScheduledStopPoint') if isinstance(objects,dict) else None
    else:
        records=payload.get('content') if isinstance(payload,dict) else payload
    if not isinstance(records,(dict,list)):raise TransitUnavailable('Transit directory format unavailable.')
    limit=500 if kind=='operators' else 2000 if kind=='lines' else 10000
    if isinstance(records,list) and len(records)>limit:raise TransitUnavailable('Transit directory exceeds the device limit. Narrow your selection.')
    result={}
    for row in items(records):
        key=_id(row,'Id','id');name=text(row.get('Name')).strip()
        if not key or not name:continue
        entry={'id':key,'name':name}
        if kind=='operators':
            entry.update(realtime_id=_id(row,'SiriOperatorRef','Id','id'),monitored=boolean(row.get('Monitored')))
        elif kind=='lines':
            entry.update(realtime_id=_id(row,'SiriLineRef','Id','id'),operator_id=_id(row,'OperatorRef'),monitored=boolean(row.get('Monitored')))
        else:
            extensions=row.get('Extensions') if isinstance(row.get('Extensions'),dict) else {}
            entry.update(platform=text(extensions.get('PlatformCode'),40),parent_id=_id(extensions,'ParentStation'),
                         station=text(extensions.get('LocationType'))=='1')
        result[key]=entry
    if records and not result:raise TransitUnavailable('Transit directory contains no usable entries.')
    return sorted(result.values(),key=lambda row:(row['name'].casefold(),row['id']))

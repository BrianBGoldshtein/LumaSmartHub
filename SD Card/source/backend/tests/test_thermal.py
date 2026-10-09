from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from luma import thermal
from luma.api import create_app


@pytest.mark.parametrize('raw,value,status', [
    (b'56478\n',56.5,'normal'), (b'69900',69.9,'normal'),
    (b'70000\n',70.0,'warm'),(b'79900',79.9,'warm'),
    (b'80000',80.0,'hot'),(b'85000',85.0,'hot'),
    (b'125000',125.0,'hot'),
])
def test_cpu_millidegrees_and_warning_bands(tmp_path,monkeypatch,raw,value,status):
    sensor=tmp_path/'temp';sensor.write_bytes(raw)
    monkeypatch.setattr(thermal,'CPU_SENSOR',sensor)
    result=thermal.read_temperature()
    assert result['celsius']==value and result['status']==status
    assert datetime.fromisoformat(result['sampled_at']).tzinfo is not None
    assert set(result)=={'celsius','status','sampled_at'}


@pytest.mark.parametrize('raw',[b'',b'0',b'-1000',b'NaN',b'56.4',b'56000 trailing',
    b'126000',b'999999999999999999999999999999999999999',b'56000\nPRIVATE',b'\xff'])
def test_invalid_sensor_is_unavailable_without_leaking_contents(tmp_path,monkeypatch,raw):
    sensor=tmp_path/'temp';sensor.write_bytes(raw)
    monkeypatch.setattr(thermal,'CPU_SENSOR',sensor)
    result=thermal.read_temperature()
    assert result['celsius'] is None and result['status']=='unavailable'


def test_missing_denied_sensor_and_later_recovery(tmp_path,monkeypatch):
    sensor=tmp_path/'temp';monkeypatch.setattr(thermal,'CPU_SENSOR',sensor)
    assert thermal.read_temperature()['celsius'] is None
    for error in [PermissionError,OSError]:
        with patch.object(Path,'open',side_effect=error):
            assert thermal.read_temperature()['status']=='unavailable'
    sensor.write_bytes(b'56478\n')
    assert thermal.read_temperature()['celsius']==56.5
    sensor.write_bytes(b'74000\n')
    assert thermal.read_temperature()['celsius']==74


@pytest.mark.asyncio
async def test_report_local_only_uncached_and_read_only(tmp_path,monkeypatch):
    app=create_app(data_dir=tmp_path/'data')
    sensor=tmp_path/'temp';sensor.write_bytes(b'56478\n')
    monkeypatch.setattr(thermal,'CPU_SENSOR',sensor)
    for host,expected in [('127.0.0.1',200),('192.0.2.10',403)]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=(host,1234)),base_url='http://127.0.0.1') as client:
            response=await client.get('/api/v1/device/temperature')
            assert response.status_code==expected
            if expected==200:
                assert response.json()['celsius']==56.5
                assert response.headers['cache-control']=='no-store'
                sensor.write_bytes(b'80000')
                assert (await client.get('/api/v1/device/temperature')).json()['status']=='hot'
                assert (await client.post('/api/v1/device/temperature',json={})).status_code==405
                assert (await client.get('/api/v1/device/temperature',headers={'Origin':'https://evil.example'})).status_code==403

"""Simulate a completed ANCS subscription in controller-only tests.

Does not connect to BlueZ. Actual wire/session coverage lives in the private
D-Bus transport tests; neither test type substitutes for physical acceptance.
"""
def authorize_primary(service, now=None):
    address = service.settings.phone_address or 'AA:BB:CC:DD:EE:FF'
    if service.settings.phone_address != address:
        service.update_settings({'phone_address': address}, now)
    runtime = service.user_bluetooth.runtime('primary')
    runtime.remote_authorized.begin(address, '/synthetic/phone', '/synthetic/source')
    runtime.remote_authorized.heartbeat(address)
    service.phone_seen(now)

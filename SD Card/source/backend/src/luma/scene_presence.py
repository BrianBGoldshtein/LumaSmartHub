"""Separate known Bluetooth absence from unavailable radio/authorization."""
from time import monotonic


def evidence(objects, address, *, authorized):
    """Plain BlueZ ObjectManager data, never RSSI or UI privacy state."""
    phone = next((obj['org.bluez.Device1'] for obj in objects.values()
                  if 'org.bluez.Device1' in obj and str(obj['org.bluez.Device1'].get('Address', '')).casefold() == address.casefold()), None)
    if not phone or not all(phone.get(key) is True for key in ('Paired', 'Bonded', 'Trusted')):
        return None
    adapter = objects.get(phone.get('Adapter'), {}).get('org.bluez.Adapter1', {})
    if adapter.get('Powered') is not True: return None
    if phone.get('Connected') is False: return False
    if phone.get('Connected') is True and phone.get('ServicesResolved') is True and authorized is True:
        return True
    return None


class ScenePresence:
    def __init__(self, *, clock=monotonic):
        self.clock = clock
        self.sample = None

    def update(self, identity, connected):
        self.sample = (identity, connected, self.clock()) if type(connected) is bool else None

    def read(self, identity):
        if not self.sample or self.sample[0] != identity or not 0 <= self.clock() - self.sample[2] <= 5:
            return None
        return self.sample[1]

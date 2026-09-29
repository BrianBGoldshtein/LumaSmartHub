"""BlueZ numeric-comparison agent; unsolicited/legacy pairing is rejected."""
from dbus_next import DBusError
from dbus_next.service import ServiceInterface, method


class PairingAgent(ServiceInterface):
    def __init__(self, device, confirm):
        super().__init__("org.bluez.Agent1")
        self.device = device
        self.confirm = confirm
        self.confirmed = False
        self.cancelled = False

    def reject(self):
        raise DBusError("org.bluez.Error.Rejected", "Pairing requires matching-code confirmation on Luma")

    @method()
    async def RequestConfirmation(self, device: 'o', passkey: 'u'):
        if self.cancelled or device != self.device or self.confirmed:
            self.reject()
        if not await self.confirm(device, passkey) or self.cancelled:
            self.reject()
        self.confirmed = True

    @method()
    def RequestAuthorization(self, device: 'o'):
        self.reject()

    @method()
    def AuthorizeService(self, device: 'o', uuid: 's'):
        self.reject()  # Pairing does not authorize unrelated audio/services.

    @method()
    def RequestPinCode(self, device: 'o') -> 's':
        self.reject()

    @method()
    def RequestPasskey(self, device: 'o') -> 'u':
        self.reject()

    @method()
    def DisplayPinCode(self, device: 'o', pincode: 's'):
        self.reject()

    @method()
    def DisplayPasskey(self, device: 'o', passkey: 'u', entered: 'q'):
        self.reject()

    @method()
    def Cancel(self):
        self.cancelled = True

    @method()
    def Release(self):
        self.cancelled = True

"""
   Copyright 2021 InfAI (CC SES)

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
from typing import Callable, Optional

import dbus
import gatt
from gatt import errors

from util import get_logger

logger = get_logger(__name__.split(".", 1)[-1])


class BLEDevice(gatt.Device):
    def __init__(self, mac: str, manager: gatt.DeviceManager, on_ready_callback: Optional[Callable],
                 on_notification_callback: Optional[Callable]):
        self.manager = manager

        self.has_on_ready_callback = False
        if on_ready_callback:
            self.on_ready_callback = on_ready_callback
            self.has_on_ready_callback = True

        self.has_on_notification_callback = False
        if on_notification_callback:
            self.on_notification_callback = on_notification_callback
            self.has_on_notification_callback = True

        super().__init__(mac, manager)

    def services_resolved(self):
        super().services_resolved()

        for service in self.services:
            logger.debug("Device offers service " + service.uuid)

        if self.has_on_ready_callback:
            self.on_ready_callback(self)

    def characteristic_value_updated(self, characteristic, value):
        logger.debug("Characteristic " + characteristic.uuid + " updated: " + value.hex())
        if self.has_on_notification_callback:
            self.on_notification_callback(self, characteristic, value)

    def characteristic_enable_notification_succeeded(self):
        logger.debug("Subscribe OK")
        super().characteristic_enable_notification_succeeded()

    def characteristic_enable_notification_failed(self):
        logger.debug("Subscribe failed")
        super().characteristic_enable_notification_failed()

    def characteristic_write_value_succeeded(self, characteristic):
        logger.debug("Write successful")
        super().characteristic_write_value_succeeded(characteristic)

    def characteristic_write_value_failed(self, characteristic, error):
        logger.error("Write failed: " + str(error))
        super().characteristic_write_value_failed(characteristic, error)

    def write(self, service_uuid: str, char_uuid: str, value: bytearray) -> bytearray:
        for service in self.services:
            if service.uuid == service_uuid:
                for char in service.characteristics:
                    if char.uuid == char_uuid:
                        logger.debug("Writing service " + service_uuid + ", characteristic " + char_uuid + ", value: " + value.hex())
                        return char.write_value(value)

    def notify(self, service_uuid: str, char_uuid: str):
        for service in self.services:
            if service.uuid == service_uuid:
                for char in service.characteristics:
                    if char.uuid == char_uuid:
                        return char.enable_notifications()

    def connect(self):
        logger.debug("Connecting " + self.mac_address)
        super().connect()

    def connect_succeeded(self):
        logger.debug("Connection established " + self.mac_address)
        super().connect_succeeded()

    def connect_failed(self, error):
        logger.debug("Connection failed " + self.mac_address + ": " + str(error))
        super().connect_failed(error)

    def disconnect(self):
        logger.debug("Disconnecting " + self.mac_address)
        super().disconnect()

    def disconnect_succeeded(self):
        logger.debug("Disconnected " + self.mac_address)
        super().disconnect_succeeded()

    def get_manufacturer_data(self):
        try:
            return self._properties.Get('org.bluez.Device1', 'ManufacturerData')
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject':
                return None
            else:
                raise _error_from_dbus_error(e)

    def get_service_data(self):
        try:
            return self._properties.Get('org.bluez.Device1', 'ServiceData')
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject':
                return None
            else:
                raise _error_from_dbus_error(e)


def _error_from_dbus_error(e):
    return {
        'org.bluez.Error.Failed': errors.Failed(e.get_dbus_message()),
        'org.bluez.Error.InProgress': errors.InProgress(e.get_dbus_message()),
        'org.bluez.Error.InvalidValueLength': errors.InvalidValueLength(e.get_dbus_message()),
        'org.bluez.Error.NotAuthorized': errors.NotAuthorized(e.get_dbus_message()),
        'org.bluez.Error.NotPermitted': errors.NotPermitted(e.get_dbus_message()),
        'org.bluez.Error.NotSupported': errors.NotSupported(e.get_dbus_message()),
        'org.freedesktop.DBus.Error.AccessDenied': errors.AccessDenied("Root permissions required")
    }.get(e.get_dbus_name(), errors.Failed(e.get_dbus_message()))

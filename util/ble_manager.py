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
import _thread
import time
import gatt

from typing import Callable, Optional, List
from util import get_logger
from util.ble_device import BLEDevice

logger = get_logger(__name__.split(".", 1)[-1])


class BLEDeviceManager(gatt.DeviceManager):
    def __init__(self, adapter_name: str, on_ready_callback: Optional[Callable] = None,
                 on_notification_callback: Optional[Callable] = None):
        self.has_on_ready_callback = False
        if on_ready_callback:
            self.on_ready_callback = on_ready_callback
            self.has_on_ready_callback = True

        self.has_on_notification_callback = False
        if on_notification_callback:
            self.on_notification_callback = on_notification_callback
            self.has_on_notification_callback = True
        super().__init__(adapter_name)

    def make_device(self, mac_address):
        return BLEDevice(mac_address, self, self.on_ready_callback if self.has_on_ready_callback else None,
                         self.on_notification_callback if self.has_on_notification_callback else None)

    def device_discovered(self, device: gatt.Device):
        logger.debug("Discovered [%s] %s" % (device.mac_address, device.alias()))

    def run(self, timeout_seconds: Optional[float] = None):
        if timeout_seconds is not None:
            _thread.start_new_thread(self.stop_after_timeout, (timeout_seconds,))
        if self._main_loop:
            return
        logger.debug("Running")
        self.is_adapter_powered = True
        super().run()

    def stop(self):
        if self._main_loop:
            logger.debug("Stopping")
            super().stop()

    def start_discovery(self, uuids: Optional[List[str]]):
        logger.debug("Start discovery")
        self.is_adapter_powered = True
        super().start_discovery(uuids)

    def stop_discovery(self):
        logger.debug("Stop discovery")
        super().stop_discovery()

    def stop_after_timeout(self, timeout_seconds: float):
        time.sleep(timeout_seconds)
        self.stop()

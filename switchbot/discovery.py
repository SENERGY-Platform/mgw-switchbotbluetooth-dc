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

import json
import threading
import time
from typing import List

import mgw_dc
from mgw_dc.dm import Device, device_state

from util import get_logger, conf, MQTTClient, diff, to_dict, init_logger
from util.ble_device import BLEDevice
from util.ble_manager import BLEDeviceManager

__all__ = ("Discovery",)
logger = get_logger(__name__.split(".", 1)[-1])


class Discovery(threading.Thread):
    def __init__(self, mqtt_client: MQTTClient):
        super().__init__(name="discovery", daemon=True)
        self._mqtt_client = mqtt_client
        self._devices: List[Device] = []
        self._current_device_is_switchbot = False

    def get_ble_devices(self) -> List[Device]:
        logger.info("Starting scan")
        devices: List[Device] = []

        manager = BLEDeviceManager(conf.Discovery.adapter, self.discovery_device_ready)
        manager.start_discovery([conf.Discovery.service_uuid])
        manager.run(conf.Discovery.scan_timeout_seconds)
        logger.info("Found {} bluetooth device(s)".format(len(manager.devices())))

        for device in manager.devices():
            device_id = conf.Discovery.device_id_prefix + device.mac_address
            if self.is_device_id_known(device_id):
                logger.info(
                    "Found curtain switchbot with mac {} and alias {}".format(device.mac_address, device.alias() + "_" + device.mac_address))
                devices.append(Device(id=device_id, name=device.alias(),
                                      type=conf.Senergy.dt_curtain, state=device_state.online))
            else:
                self._current_device_is_switchbot = False
                device.connect()
                manager.run(conf.Discovery.connect_timeout_seconds)
                if self._current_device_is_switchbot:
                    logger.info(
                        "Found curtain switchbot with mac {} and alias {}".format(device.mac_address, device.alias()))
                    devices.append(Device(id=device_id, name=device.alias(),
                                          type=conf.Senergy.dt_curtain, state=device_state.online))
        logger.info("Scan completed, found {} switchbots".format(str(len(devices))))
        return devices

    def is_device_id_known(self, device_id: str):
        for d in self._devices:
            if d.id == device_id:
                return True
        return False

    def discovery_device_ready(self, ble: BLEDevice):
        for service in ble.services:
            if service.uuid == conf.Discovery.service_uuid:
                self._current_device_is_switchbot = True
        ble.disconnect()
        ble.manager.stop()

    def _handle_new_device(self, device: Device):
        try:
            logger.info("adding '{}'".format(device.id))
            self._mqtt_client.subscribe(topic=mgw_dc.com.gen_command_topic(device.id), qos=1)
            self._mqtt_client.publish(
                topic=mgw_dc.dm.gen_device_topic(conf.Client.id),
                payload=json.dumps(mgw_dc.dm.gen_set_device_msg(device)),
                qos=1
            )
        except Exception as ex:
            logger.error("adding '{}' failed - {}".format(device.id, ex))

    def _handle_missing_device(self, device: Device):
        device.state = device_state.offline
        try:
            logger.info("setting '{}' offline ...".format(device.id))
            self._mqtt_client.publish(
                topic=mgw_dc.dm.gen_device_topic(conf.Client.id),
                payload=json.dumps(mgw_dc.dm.gen_set_device_msg(device)),
                qos=1
            )
            self._mqtt_client.unsubscribe(topic=mgw_dc.com.gen_command_topic(device.id))
        except Exception as ex:
            logger.error("removing '{}' failed - {}".format(device.id, ex))

    def _handle_existing_device(self, device: Device):
        try:
            logger.info("updating '{}' ...".format(device.id))
            self._mqtt_client.publish(
                topic=mgw_dc.dm.gen_device_topic(conf.Client.id),
                payload=json.dumps(mgw_dc.dm.gen_set_device_msg(device)),
                qos=1
            )
        except Exception as ex:
            logger.error("updating '{}' failed - {}".format(device.id, ex))

    def _refresh_devices(self):
        try:
            stored_devices = to_dict(self._devices)
            self._devices = self.get_ble_devices()
            ble_devices = to_dict(self._devices)

            new_devices, missing_devices, existing_devices = diff(stored_devices, ble_devices)
            if new_devices:
                for device_id in new_devices:
                    self._handle_new_device(ble_devices[device_id])
            if missing_devices:
                for device_id in missing_devices:
                    self._handle_missing_device(stored_devices[device_id])
            if existing_devices:
                for device_id in existing_devices:
                    self._handle_existing_device(stored_devices[device_id])
        except Exception as ex:
            logger.error("refreshing devices failed - {}".format(ex))

    def run(self) -> None:
        while not self._mqtt_client.connected():
            time.sleep(0.3)
        logger.info("starting {} ...".format(self.name))
        last_ble_check = time.time()
        self._refresh_devices()
        while True:
            if time.time() - last_ble_check > conf.Discovery.scan_delay:
                last_ble_check = time.time()
                self._refresh_devices()
            time.sleep(conf.Discovery.scan_delay / 100)  # at most 1 % too late

    def publish_devices(self):
        for device in self._devices:
            try:
                self._mqtt_client.publish(
                    topic=mgw_dc.dm.gen_device_topic(conf.Client.id),
                    payload=json.dumps(mgw_dc.dm.gen_set_device_msg(device)),
                    qos=1
                )
            except Exception as ex:
                logger.error("setting device '{}' failed - {}".format(device.id, ex))


if __name__ == "__main__":
    init_logger(conf.Logger.level)
    discovery = Discovery(mqtt_client=None)
    discovery.get_ble_devices()

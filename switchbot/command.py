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
import typing
import time
import gatt
import mgw_dc

from util import conf, get_logger, MQTTClient, init_logger
from util.ble_device import BLEDevice
from util.ble_manager import BLEDeviceManager

logger = get_logger(__name__.split(".", 1)[-1])

__all__ = ("Command",)

curtain_handle = 16

response_code_ok = 0x01
response_codes = {
    0x02: "ERROR",
    0x03: "BUSY",
    0x04: "Communication protocol version incompatible",
    0x05: "Device does not support this Command",
    0x06: "Device is low power",
    0x0D: "This command is not supported in the current mode",
    0x0E: "Disconnected from the device that needs to stay connected",
}

charging_codes = {
    0: "not charging",
    1: "adapter charging",
    2: "solar panel charging",
    3: "adapter connected & fully charged",
    4: "solar panel connected & fully charged",
    5: "solar panel connected, but not charging",
    6: "hardware error",
}


class Command:
    def __init__(self, mqtt_client: MQTTClient):
        self.__mqtt_client = mqtt_client
        self.command_result: bytearray = bytearray()
        self.connection_ok = False
        self.command_handlers = {
            conf.Senergy.service_status: self.service_status,
            conf.Senergy.service_command: self.service_set_position,
        }
        self.command_requests = 0
        self.position_to = 101
        self.retry = 0

    def reset_for_next_cmd(self):
        self.command_requests = 0
        self.command_result = bytearray()
        self.connection_ok = False
        self.position_to = 101
        self.retry = 0

    def handle_command(self, prefixed_device_id: str, service: str, payload: typing.AnyStr):
        device_id = prefixed_device_id.removeprefix(conf.Discovery.device_id_prefix)

        payload = json.loads(payload)
        command_id = payload["command_id"]
        if len(payload["data"]) == 0:
            payload = {}
        else:
            payload = json.loads(payload["data"])
        if service not in self.command_handlers:
            logger.error("Unimplemented service " + service)
            return
        self.reset_for_next_cmd()
        try:
            result = self.run_command(device_id, service, payload)
        except Exception as ex:
            logger.error("Command failed: {}".format(ex))
            return
        response = {"command_id": command_id, "data": json.dumps(result).replace("'", "\"")}
        self.__mqtt_client.publish(mgw_dc.com.gen_response_topic(prefixed_device_id, service),
                                   json.dumps(response).replace("'", "\""), 2)

    def run_command(self, device_id: str, service: str, payload: dict):
        try:
            result = self.command_handlers[service](device_id, payload)
        except Exception as ex:
            logger.error("Command execution failed: {}".format(ex))
            if self.retry < conf.Discovery.command_retries:
                self.retry += 1
                logger.info("Command retry #" + str(self.retry) + " in " + str(conf.Discovery.command_retry_wait_seconds) + " seconds")
                time.sleep(conf.Discovery.command_retry_wait_seconds)
                return self.run_command(device_id, service, payload)
            raise RuntimeError("Out of retries")
        return result

    def service_status(self, device_id: str, _: None = None) -> dict:
        manager = BLEDeviceManager(adapter_name=conf.Discovery.adapter)
        device = BLEDevice(device_id, manager, self.service_status_ready_callback,
                           self.service_status_notification_callback)
        device.connect()
        manager.run(conf.Discovery.connect_timeout_seconds + conf.Discovery.command_timeout_seconds)
        if not self.connection_ok:
            raise RuntimeError("Could not establish connection")
        logger.debug("Result: " + self.command_result.hex())
        logger.debug("Manufacturer Data: " + json.dumps(device.get_manufacturer_data()))
        service_data = device.get_service_data()[conf.Discovery.service_data_uuid]
        logger.debug("Service Data: " + str(service_data))

        if self.command_result[0] != response_code_ok:
            raise RuntimeError(get_err_msg(self.command_result[0]))
        result = {}

        if service_data[0] == 99:
            result['bluetooth_mode'] = 'advertising'
        elif service_data[0] == 67:
            result['bluetooth_mode'] = 'pair'
        else:
            result['bluetooth_mode'] = 'unknown: ' + str(service_data[0])

        result['connection_allowed'] = service_data[1] >> 7 == 1
        result['calibrated'] = (service_data[1] & 0b01000000) >> 6 == 1
        result['battery'] = service_data[2] & 0b01111111
        result['moving'] = service_data[3] >> 7 == 1
        result['position'] = service_data[3] & 0b0111111
        result['light_level'] = (service_data[4] & 0b11110000) >> 4
        result['chain_length'] = service_data[4] & 0b00001111

        result['firmware'] = self.command_result[2]
        if self.command_result[4] >> 7 == 0:
            result['direction'] = 'open to left'
        else:
            result['direction'] = 'open to right'
        result['touch_and_go_enabled'] = (self.command_result[4] & 0b01000000) >> 6 == 1
        result['lighting_effect_enabled'] = (self.command_result[4] & 0b00100000) >> 5 == 1
        result['fault'] = (self.command_result[4] & 0b00001000) >> 3 == 1
        result['solar_plugged_in'] = self.command_result[5] >> 7 == 1
        result['number_timers'] = self.command_result[7]

        self.command_result = self.command_result[8:]  # shift away previous response
        if self.command_result[0] != response_code_ok:
            raise RuntimeError(get_err_msg(self.command_result[0]))
        result['delay_action'] = self.command_result[1] >> 7 == 1
        result['number_light_actions'] = self.command_result[1] & 0b00001111
        if (self.command_result[2] & 0b11110000) >> 4 == 0:
            result['action_mode'] = 'performance'
        elif (self.command_result[2] & 0b11110000) >> 4 == 1:
            result['action_mode'] = 'silent'
        else:
            result['action_mode'] = 'invalid: ' + str((self.command_result[2] & 0b11110000) >> 4)

        self.command_result = self.command_result[8:]  # shift away previous response
        if self.command_result[0] != response_code_ok:
            raise RuntimeError(get_err_msg(self.command_result[0]))
        if self.command_result[3] in charging_codes:
            result['charging_device_0'] = charging_codes[self.command_result[3]]
        else:
            result['charging_device_0'] = "unknown: " + str(self.command_result[3])

        if self.command_result[6] in charging_codes:
            result['charging_device_1'] = charging_codes[self.command_result[6]]
        else:
            result['charging_device_1'] = "unknown: " + str(self.command_result[6])

        logger.debug(json.dumps(result))

        return result

    @staticmethod
    def service_status_ready_callback(device: BLEDevice):
        device.notify(conf.Discovery.service_uuid, conf.Discovery.receiving_char_uuid)
        device.write(conf.Discovery.service_uuid, conf.Discovery.sending_char_uuid, bytearray(b'\x57\x02'))

    def service_status_notification_callback(self, device: BLEDevice, _: gatt.Characteristic,
                                             value: bytearray):
        if self.command_requests == 0:
            self.command_result = value[:8]
            device.write(conf.Discovery.service_uuid, conf.Discovery.sending_char_uuid,
                         bytearray(b'\x57\x0F\x46\x81\x01'))
        elif self.command_requests == 1:
            if not isinstance(self.command_result, bytearray):
                self.command_result = bytearray(self.command_result)
            self.command_result.extend(value[:8])
            device.write(conf.Discovery.service_uuid, conf.Discovery.sending_char_uuid,
                         bytearray(b'\x57\x0F\x46\x04\x02'))
        else:
            self.command_result.extend(value[:7])
            self.connection_ok = True
            device.disconnect()
            device.manager.stop()

        self.command_requests += 1

    def service_set_position(self, device_id: str, payload: dict) -> dict:
        if "target_position" not in payload:
            raise RuntimeError("Missing input")
        self.position_to = payload["target_position"]
        manager = BLEDeviceManager(adapter_name=conf.Discovery.adapter)
        device = BLEDevice(device_id, manager, self.service_set_position_ready_callback,
                           self.service_set_position_notification_callback)
        device.connect()
        manager.run(conf.Discovery.connect_timeout_seconds + conf.Discovery.command_timeout_seconds)
        if not self.connection_ok:
            raise RuntimeError("Could not establish connection")
        logger.debug("Result: " + self.command_result.hex())
        if self.command_result[0] != response_code_ok:
            raise RuntimeError(get_err_msg(self.command_result[0]))
        return {}

    def service_set_position_ready_callback(self, device: BLEDevice):
        device.notify(conf.Discovery.service_uuid, conf.Discovery.receiving_char_uuid)
        payload = bytearray(b'\x57\x0F\x45\x01\x05\xFF')
        payload.append(self.position_to)
        device.write(conf.Discovery.service_uuid, conf.Discovery.sending_char_uuid, payload)

    def service_set_position_notification_callback(self, device: BLEDevice, __: gatt.Characteristic,
                                             value: bytearray):
        self.connection_ok = True
        self.command_result = value
        device.disconnect()
        device.manager.stop()


def get_err_msg(code: int) -> str:
    err_msg = "Code " + str(code) + ": "
    if code in response_codes:
        err_msg += response_codes[code]
    return err_msg


if __name__ == "__main__":
    import time
    mac = "00:11:22:33:44:55"  # adjust for testing with actual curtain bot
    init_logger(conf.Logger.level)
    cmd = Command(None)

    logger.info("Getting status")
    cmd.reset_for_next_cmd()
    try:
        cmd.service_status(mac)
    except Exception as ex:
        logger.error(str(ex))

    time.sleep(10)

    logger.info("Setting position to 0%")
    cmd.reset_for_next_cmd()
    try:
        cmd.service_set_position(mac, {"target_position": 0})
    except Exception as ex:
        logger.error(str(ex))

    time.sleep(10)

    logger.info("Getting status")
    cmd.reset_for_next_cmd()
    try:
        cmd.service_status(mac)
    except Exception as ex:
        logger.error(str(ex))

    time.sleep(10)

    logger.info("Setting position to 10%")
    cmd.reset_for_next_cmd()
    try:
        cmd.service_set_position(mac, {"target_position": 10})
    except Exception as ex:
        logger.error(str(ex))

    time.sleep(10)

    logger.info("Getting status")
    cmd.reset_for_next_cmd()
    try:
        cmd.service_status(mac)
    except Exception as ex:
        logger.error(str(ex))


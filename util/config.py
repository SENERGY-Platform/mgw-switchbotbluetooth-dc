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

__all__ = ("conf",)

import simple_env_var


@simple_env_var.configuration
class Conf:
    @simple_env_var.section
    class MsgBroker:
        host = "message-broker"
        port = 1883

    @simple_env_var.section
    class Logger:
        level = "debug"
        enable_mqtt = False

    @simple_env_var.section
    class Client:
        clean_session = False
        keep_alive = 10
        id = "switchbotcloud-dc"

    @simple_env_var.section
    class Discovery:
        scan_timeout_seconds = 5
        connect_timeout_seconds = 2
        command_timeout_seconds = 3
        scan_delay = 1800
        command_retries = 2
        command_retry_wait_seconds = 3
        device_id_prefix = "switchbotbluetooth-"
        adapter = "hci0"
        service_uuid = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
        receiving_char_uuid = "cba20003-224d-11e6-9fb8-0002a5d5c51b"
        sending_char_uuid = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
        service_data_uuid = "00000d00-0000-1000-8000-00805f9b34fb"

    @simple_env_var.section
    class StartDelay:
        enabled = False
        min = 5
        max = 20

    @simple_env_var.section
    class Senergy:
        dt_curtain = "urn:infai:ses:device-type:38cf9c47-aebf-481d-8b17-5379e191a470"
        service_status = "status"
        service_command = "set_position"


conf = Conf()

if not conf.Senergy.dt_curtain:
    exit('Please provide SENERGY device types')

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


from util import init_logger, conf, MQTTClient, handle_sigterm, delay_start, Router
from switchbot import Discovery, Command
import signal


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    if conf.StartDelay.enabled:
        delay_start(conf.StartDelay.min, conf.StartDelay.max)
    init_logger(conf.Logger.level)
    try:
        mqtt_client = MQTTClient()
        discovery = Discovery(mqtt_client=mqtt_client)
        command = Command(mqtt_client=mqtt_client)
        router = Router(refresh_callback=discovery.publish_devices, command_callback=command.handle_command)
        mqtt_client.on_connect = discovery.publish_devices
        mqtt_client.on_message = router.route
        discovery.start()
        mqtt_client.start()
    finally:
        pass

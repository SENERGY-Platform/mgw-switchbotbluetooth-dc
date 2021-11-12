FROM python:3-buster

LABEL org.opencontainers.image.source https://github.com/SENERGY-Platform/mgw-switchbotbluetooth-dc


RUN apt-get update && apt-get install -y libgirepository1.0-dev libdbus-1-dev

WORKDIR /usr/src/app

COPY . .
RUN pip install --extra-index-url https://www.piwheels.org/simple --no-cache-dir -r requirements.txt

CMD [ "python", "-u", "./dc.py"]

# Usage:
# docker build -t test .
# docker run -v /var/run/dbus/system_bus_socket:/var/run/dbus/system_bus_socket test

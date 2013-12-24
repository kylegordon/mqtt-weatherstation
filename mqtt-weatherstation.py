#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

__author__ = "Kyle Gordon"
__copyright__ = "Copyright (C) Kyle Gordon"

import mosquitto
import os
import logging
import signal
import socket
import time
import serial
import sys

import mosquitto
import ConfigParser

# Read the config file
config = ConfigParser.RawConfigParser()
config.read("/etc/mqtt-weatherstation/mqtt-weatherstation.cfg")

# Use ConfigParser to pick out the settings
DEBUG = config.getboolean("global", "debug")
LOGFILE = config.get("global", "logfile")
SERIAL = config.get("global", "serial")
BAUD = config.get("global", "baud")
MQTT_HOST = config.get("global", "mqtt_host")
MQTT_PORT = config.getint("global", "mqtt_port")
MQTT_TOPIC = "/raw/" + socket.getfqdn() + "/weatherstationFSK/"

client_id = "weatherstation_%d" % os.getpid()
mqttc = mosquitto.Mosquitto(client_id)

LOGFORMAT = '%(asctime)-15s %(message)s'

if DEBUG:
    logging.basicConfig(filename=LOGFILE, level=logging.DEBUG, format=LOGFORMAT)
else:
    logging.basicConfig(filename=LOGFILE, level=logging.INFO, format=LOGFORMAT)

logging.info('Starting mqtt-weatherstation')
logging.info('INFO MODE')
logging.debug('DEBUG MODE')

def cleanup(signum, frame):
     """
     Signal handler to ensure we disconnect cleanly 
     in the event of a SIGTERM or SIGINT.
     """
     logging.info("Disconnecting from broker")
     # FIXME - This status topis too far up the hierarchy.
     mqttc.publish("/status/" + socket.getfqdn(), "Offline")
     mqttc.disconnect()
     logging.info("Exiting on signal %d", signum)
     sys.exit(signum)

def connect():
    """
    Connect to the broker, define the callbacks, and subscribe
    """
    result = mqttc.connect(MQTT_HOST, MQTT_PORT, 60, True)
    if result != 0:
        logging.info("Connection failed with error code %s. Retrying", result)
        time.sleep(10)
        connect()

    #define the callbacks
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect

    mqttc.subscribe(MQTT_TOPIC, 2)

def open_serial(port,speed):
    """
    Open the serial port
    """
    global ser
    ser = serial.Serial(SERIAL, BAUD)

def on_connect(result_code):
     """
     Handle connections (or failures) to the broker.
     """
     ## FIXME - needs fleshing out http://mosquitto.org/documentation/python/
     if result_code == 0:
        logging.info("Connected to broker")
        mqttc.publish("/status/" + socket.getfqdn(), "Online")
     else:
        logging.warning("Something went wrong")
        cleanup()

def on_disconnect(result_code):
     """
     Handle disconnections from the broker
     """
     if result_code == 0:
        logging.info("Clean disconnection")
     else:
        logging.info("Unexpected disconnection! Reconnecting in 5 seconds")
        logging.debug("Result code: %s", result_code)
        time.sleep(5)
        connect()
        main_loop()

def on_message(msg):
    """
    What to do once we receive a message
    """
    logging.debug("Received: " + msg.topic)
    if msg.topic == "/status" and msg.payload == "status?":
        mqttc.publish("/status/" + socket.getfqdn(), "Online")

def main_loop():
    """
    The main loop in which we stay connected to the broker
    """
    while mqttc.loop() == 0:
        msg = ser.readline()
        items = msg.split(",")
        try:
            logging.debug("0th element is %s", items[0])
	    if (items[0] == "[weatherstationFSK]"):
		logging.info("Arduino reset")
		mqttc.publish(MQTT_TOPIC + "/status", "Arduino reset")
	    else:
		logging.debug("Received a list of " + str(len(items)) + " items")
	        logging.debug(items)
	    	# Take the incoming split string, get the relevant key/value, get the value, and strip it of units
	    	temperature = items[1].split("=")[1].strip().strip("`C")
		rel_humidity = items[2].split("=")[1].strip().strip("%")
		wind_velocity = items[3].split("=")[1].strip().strip("m/s")
		wind_maximum = items[4].split("=")[1].strip().strip("m/s")
		wind_direction = items[5].split("=")[1].strip()
		rainfall = items[6].split("=")[1].strip().strip("mm")

                mqttc.publish(MQTT_TOPIC + "/temperature/", str(temperature))
		mqttc.publish(MQTT_TOPIC + "/relative_humidity/", str(rel_humidity))
                mqttc.publish(MQTT_TOPIC + "/wind_velocity/", str(wind_velocity))
		mqttc.publish(MQTT_TOPIC + "/wind_maximum/", str(wind_maximum))
		mqttc.publish(MQTT_TOPIC + "/wind_direction/", str(wind_direction))
		mqttc.publish(MQTT_TOPIC + "/rainfall/", str(rainfall))

        except IndexError:
            logging.info("Caught a null line. Nothing to worry about")

# Use the signal module to handle signals
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

# Connect to the broker, open the serial port, and enter the main loop
open_serial("/dev/ttyUSB0", 57600)
connect()
main_loop()

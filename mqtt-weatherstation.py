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

APPNAME = "mqtt-weatherstation"
PRESENCETOPIC = "clients/" + socket.getfqdn() + "/" + APPNAME + "/state"
client_id = APPNAME + "_%d" % os.getpid()
mqttc = mosquitto.Mosquitto(client_id)

LOGFORMAT = '%(asctime)-15s %(message)s'

if DEBUG:
    logging.basicConfig(filename=LOGFILE,
                        level=logging.DEBUG,
                        format=LOGFORMAT)
else:
    logging.basicConfig(filename=LOGFILE,
                        level=logging.INFO,
                        format=LOGFORMAT)

logging.info("Starting " + APPNAME)
logging.info("INFO MODE")
logging.debug("DEBUG MODE")

# All the MQTT callbacks start here


def on_publish(mosq, obj, mid):
    """
    What to do when a message is published
    """
    logging.debug("MID " + str(mid) + " published.")


def on_subscribe(mosq, obj, mid, qos_list):
    """
    What to do in the event of subscribing to a topic"
    """
    logging.debug("Subscribe with mid " + str(mid) + " received.")


def on_unsubscribe(mosq, obj, mid):
    """
    What to do in the event of unsubscribing from a topic
    """
    logging.debug("Unsubscribe with mid " + str(mid) + " received.")


def on_connect(mosq, obj, result_code):
    """
    Handle connections (or failures) to the broker.
    This is called after the client has received a CONNACK message
    from the broker in response to calling connect().
    The parameter rc is an integer giving the return code:

    0: Success
    1: Refused – unacceptable protocol version
    2: Refused – identifier rejected
    3: Refused – server unavailable
    4: Refused – bad user name or password (MQTT v3.1 broker only)
    5: Refused – not authorised (MQTT v3.1 broker only)
    """
    logging.debug("on_connect RC: " + str(result_code))
    if result_code == 0:
        logging.info("Connected to %s:%s", MQTT_HOST, MQTT_PORT)
        # Publish retained LWT as per
        # http://stackoverflow.com/q/97694
        # See also the will_set function in connect() below
        mqttc.publish(PRESENCETOPIC, "1", retain=True)
        process_connection()
    elif result_code == 1:
        logging.info("Connection refused - unacceptable protocol version")
        cleanup()
    elif result_code == 2:
        logging.info("Connection refused - identifier rejected")
        cleanup()
    elif result_code == 3:
        logging.info("Connection refused - server unavailable")
        logging.info("Retrying in 30 seconds")
        time.sleep(30)
    elif result_code == 4:
        logging.info("Connection refused - bad user name or password")
        cleanup()
    elif result_code == 5:
        logging.info("Connection refused - not authorised")
        cleanup()
    else:
        logging.warning("Something went wrong. RC:" + str(result_code))
        cleanup()


def on_disconnect(mosq, obj, result_code):
    """
    Handle disconnections from the broker
    """
    if result_code == 0:
        logging.info("Clean disconnection")
    else:
        logging.info("Unexpected disconnection! Reconnecting in 5 seconds")
        logging.debug("Result code: %s", result_code)
        time.sleep(5)


def on_message(mosq, obj, msg):
    """
    What to do when the client recieves a message from the broker
    """
    logging.debug("Received: " + msg.payload +
                  " received on topic " + msg.topic +
                  " with QoS " + str(msg.qos))
    process_message(msg)


def on_log(mosq, obj, level, string):
    """
    What to do with debug log output from the MQTT library
    """
    logging.debug(string)

# End of MQTT callbacks


def cleanup(signum, frame):
    """
    Signal handler to ensure we disconnect cleanly
    in the event of a SIGTERM or SIGINT.
    """
    logging.info("Disconnecting from broker")
    # Publish a retained message to state that this client is offline
    mqttc.publish(PRESENCETOPIC, "0", retain=True)
    mqttc.disconnect()
    mqttc.loop_stop()
    logging.info("Exiting on signal %d", signum)
    sys.exit(signum)


def connect():
    """
    Connect to the broker, define the callbacks, and subscribe
    This will also set the Last Will and Testament (LWT)
    The LWT will be published in the event of an unclean or
    unexpected disconnection.
    """
    logging.debug("Connecting to %s:%s", MQTT_HOST, MQTT_PORT)
    # Set the Last Will and Testament (LWT) *before* connecting
    mqttc.will_set(PRESENCETOPIC, "0", qos=0, retain=True)
    result = mqttc.connect(MQTT_HOST, MQTT_PORT, 60, True)
    if result != 0:
        logging.info("Connection failed with error code %s. Retrying", result)
        time.sleep(10)
        connect()

    # Define the callbacks
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_publish = on_publish
    mqttc.on_subscribe = on_subscribe
    mqttc.on_unsubscribe = on_unsubscribe
    mqttc.on_message = on_message
    if DEBUG:
        mqttc.on_log = on_log

    mqttc.loop_start()


def process_connection():
    """
    What to do when a new connection is established
    """
    logging.debug("Processing connection")


def process_message(msg):
    """
    What to do with the message that's arrived
    """
    logging.debug("Received: %s", msg.topic)


def open_serial(port, speed):
    """
    Open the serial port and flush any waiting input.
    """
    global ser
    try:
        logging.info("Connecting to " + SERIAL + " at " + BAUD + " baud")
        ser = serial.Serial(SERIAL, BAUD)
        ser.flushInput()
    except:
        logging.warning("Unable to connect to " +
                        SERIAL + " at " +
                        BAUD + " baud")
        raise SystemExit


def main_loop():
    """
    The main loop in which we read the serial port
    and handle the incoming data
    """
    while True:
        # Read the serial input, and split the CSV list up
        msg = ser.readline()
        items = msg.split(",")
        try:
            logging.debug("0th element is %s", items[0])
            # Catch a startup message
            if (items[0] == "[weatherstationFSK]"):
                logging.info("Arduino reset")
                mqttc.publish(MQTT_TOPIC + "/status", "Arduino reset")
            else:
                logging.debug("Received a list of " +
                              str(len(items)) + " items")
                logging.debug(items)
                # Take the incoming split string, get the relevant key/value pair,
                # take the value, and strip it of units
                temperature = items[1].split("=")[1].strip().strip("`C")
                rel_humidity = items[2].split("=")[1].strip().strip("%")
                wind_velocity = items[3].split("=")[1].strip().strip("m/s")
                wind_maximum = items[4].split("=")[1].strip().strip("m/s")
                wind_direction = items[5].split("=")[1].strip()
                rainfall = items[6].split("=")[1].strip().strip("mm")
                
                # Publish the resultant values over MQTT
                mqttc.publish(MQTT_TOPIC + "temperature/",
                              str(temperature))
                mqttc.publish(MQTT_TOPIC + "relative_humidity/",
                              str(rel_humidity))
                mqttc.publish(MQTT_TOPIC + "wind_velocity/",
                              str(wind_velocity))
                mqttc.publish(MQTT_TOPIC + "wind_maximum/",
                              str(wind_maximum))
                mqttc.publish(MQTT_TOPIC + "wind_direction/",
                              str(wind_direction))
                mqttc.publish(MQTT_TOPIC + "rainfall/",
                              str(rainfall))

        except IndexError:
            logging.info("Caught a null line. Nothing to worry about")

# Use the signal module to handle signals
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

# Connect to the broker, open the serial port, and enter the main loop
open_serial("/dev/ttyUSB0", 57600)
connect()
# Try to start the main loop
try:
    main_loop()
except KeyboardInterrupt:
    logging.info("Interrupted by keypress")
    sys.exit(0)
    main_loop()

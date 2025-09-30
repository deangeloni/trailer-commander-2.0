import os
import network, xbee, time, json, gc
from machine import Pin
from mqtt import MQTTClient
from gps import moo_serial
from i2c import i2c_sensors


print(" ***** Starting from the top", end="")
BUILD_NO = "104F.1"
BUILD_DATE = "07-12-2025"

# endpoint parameters.
SERVER = "mqtt.moovalot.com"
SVR_PORT = 8883
TOPIC = "moovalot/trailer/"

print(" | setup MQTT Variables", end="")
# LOCK DURATIONS and Siren Chirp Duration
LOCK_PULSE = .25  # changed from .5 on 12/13
SIREN_PULSE = .25

# default minutes between position updates.
Run_Time = 60

# Define Module Pins
print(" | setup PIN Variables", end="")
PIN_TOOLBOX_TRIGGER = "D0"
PIN_LOCK_NOTICE = "D2"
PIN_LOCK = "D3"
PIN_UNLOCK = "D7"
PIN_PLUGGED_HOT = "D5"
PIN_SIREN = "D9"
PIN_Fan_OUTPUT = "D10"

# Define Module Pin status
###################### Pin 12 / CTS /  D7 | DIO 7 |
UNLOCK_TRAILER = Pin(PIN_UNLOCK, mode=Pin.OUT, pull=Pin.PULL_UP)
###################### Pin 17 / D3   | DIO3
LOCK_TRAILER = Pin(PIN_LOCK, mode=Pin.OUT, pull=Pin.PULL_UP)
#LOCK_TRAILER = Pin.board.D3

SIREN_TRAILER =  Pin(PIN_SIREN, Pin.OUT, value=0)
Fan_OUTPUT =     Pin(PIN_Fan_OUTPUT, Pin.OUT, value=0)

LOCK_NOTICE = Pin(PIN_LOCK_NOTICE, Pin.IN, Pin.PULL_UP)
PLUGGED_HOT = Pin(PIN_PLUGGED_HOT, Pin.IN, Pin.PULL_DOWN)  #Trailer Hot Wire
TOOLBOX_TRIGGER = (Pin(PIN_TOOLBOX_TRIGGER, Pin.IN, Pin.PULL_UP))

print(" -- SUCCESS", end="")

print(" | Global  Variables", end="")
LOCK_STATUS = "LOCKED"
GONOW = False
GONOW_MSG = "STARTING"

START_TIME = ""
START_TIME_RAW = ""
SCRIPT_EPOCH_START_TIME = time.time()
LAST_STATUS = ""
START_TIME_MainRoutine = ""
START_TIME_SubRoutine = ""

RENT_STATUS = False

ALARM_STATUS = False
ALARM_MSG = ""
ALARM_ACTIVATED_TIME = 0
ALARM_DURATION = 10
ALARM_REPORT = 0  # 0=stale, 1=alarmon, 2=alarmoff

CORAL_ID = ""
CORAL_NAME = ""
CORAL_ADDR = ""
CORAL_LAT = ""
CORAL_LON = ""
CORAL_RAD = ""

MAINTENANCE_MODE = True  # default to True. avoids alarming
TOOLBOX_STATE = 2
### Reduces noise during start up
START_ROUTINE = True
START_ROUTINE_Time = 45

FAN_THRESHOLD = 150  # temp to engage fan
FAN_STATUS = False
FAN_RUNTIME = 30  # how long Fan runs
FAN_START_TIME = 0

# Add these at the top if not already present from previous reviews
LOCK_CMD_LOCK = 1
LOCK_CMD_UNLOCK = 2
ALARM_CMD_ON = 1
ALARM_CMD_OFF = 2
print(" Done")

# Setup I2c Bus ########################################
sensors = i2c_sensors()

def get_cell_strength():
    try:
        css = xbee.atcmd("DB")
        if css > 85:
            return "Poor : rssi -" + str(css)
        if css > 75:
            return "Fair : rssi -" + str(css)
        if css > 65:
            return "Good : rssi -" + str(css)
        if css > 1:
            return "Excellent : rssi -" + str(css)
        return "NA"
    except:
        return "NA"


def get_temp():
    try:
        tp = xbee.atcmd('TP')
        if tp > 0x7FFF:
            tp = tp - 0x10000
        temp = (tp * 9.0 / 5.0 + 32.0)
        return temp
    except Exception as e:
        print(f" !! ERROR getting modem temperature: {e}")
        return 0


def timestamp(t=None):  # Obtain and output the current time.
    return "%04u-%02u-%02u %02u:%02u:%02u" % time.localtime(t)[0:6]


def check_sms(c):
    # Return the incoming message, or "None" if there isn't one.
    # msg = c.sms_receive()
    # if msg:
    #     print('  -- SMS SMS SMS -- SMS received at %s from %s:\n%s' %
    #         (timestamp(msg['timestamp']), msg['sender'], msg['message']))
    return 1

def beep(cycles, pulse_length):
    global START_ROUTINE, START_ROUTINE_Time
    if START_ROUTINE is False:
        x = 1
        while x <= cycles:
            SIREN_TRAILER.value(1)
            time.sleep(pulse_length)
            SIREN_TRAILER.value(0)
            time.sleep(pulse_length)
            x = x + 1

def dynamic_reporting(in_speed) -> int:
    try:
        speed = float(in_speed)
        global Run_Time
        if speed > 65:
            Run_Time = 15
        elif speed > 35:
            Run_Time = 20
        elif speed > 15:
            Run_Time = 20
        elif speed > 5:
            Run_Time = 30
        else:
            Run_Time = 90
        print(" -- Runtime set to : " + str(Run_Time) + " seconds")
        return Run_Time
    except:
        return 20


def lock_trailer(opt, siren):
    global GONOW, GONOW_MSG
    if opt == 2:
        UNLOCK_TRAILER.value(1)
        time.sleep(LOCK_PULSE)
        UNLOCK_TRAILER.value(0)
        if siren: beep(2, SIREN_PULSE)
        print(" Successful  <<<<   Unlock Complete", end="")
    elif opt == 1:
        LOCK_TRAILER.value(1)
        time.sleep(LOCK_PULSE)
        LOCK_TRAILER.value(0)
        if START_ROUTINE is False:
            if siren: beep(1, SIREN_PULSE)
        print(" Successful <<<<  LOCK Complete", end="")

    LS = "LOCKED" if LOCK_NOTICE.value() == 0 else "UNLOCKED"
    print(f" | -- Current Lock State: {LS}", end="")

    return 0


def alarm(opt, msg):
    global ALARM_MSG, ALARM_STATUS, ALARM_ACTIVATED_TIME, GONOW, GONOW_MSG, ALARM_REPORT, ALARM_DURATION, START_ROUTINE
    if opt == 1 and MAINTENANCE_MODE is False and ALARM_STATUS is False and RENT_STATUS is False and START_ROUTINE is False:
        # ACTIVATE ALARM
        print(" !! ALARM ACTIVATED -- ")
        ALARM_STATUS = True
        ALARM_ACTIVATED_TIME = time.time()
        ALARM_MSG = str(msg)
        # Lock Trailer ------------
        lock_trailer(1, False)
        SIREN_TRAILER.value(1)
        GONOW = True
        GONOW_MSG = "CMD:ALARM:" + str(msg)
        ALARM_REPORT = 1
    if opt == 2:
        print(" !! ALARM DE-ACTIVATED -- ", end="")
        ALARM_STATUS = False
        ALARM_ACTIVATED_TIME = 0
        ALARM_MSG = ""
        # Turn Off Siren
        SIREN_TRAILER.value(0)
        GONOW = True
        GONOW_MSG = "CMD:UNALARM:" + str(msg)
        ALARM_REPORT = 2
        ALARM_DURATION = 20
        print(f"ACTIVATED -- {ALARM_REPORT}")


def get_current_time():
    ct = time.localtime()
    yr = ct[0]
    mo = ct[1]
    dy = ct[2]
    hr = ct[3]
    mn = ct[4]
    ss = ct[5]
    formatted_time = f"{yr:04d}-{mo:02d}-{dy:02d} {hr:02d}:{mn:02d}:{ss:02d}"
    return formatted_time


def get_alarm_run_time():
    try:
        #print(" XXX - Getting Alarm Run Time |  Started--- @{}".format(ALARM_ACTIVATED_TIME))
        if ALARM_STATUS and ALARM_ACTIVATED_TIME != 0:
            cur_time = time.time()
            delta_time = cur_time - ALARM_ACTIVATED_TIME
            #print(" XXX - Getting Alarm Run Time |  Current Time--- " + str(cur_time))
            #print(" XXX - Getting Alarm Run Time |  Delta Time--- " + str(delta_time))
            return delta_time
        else:
            return 0
    except Exception as E:
        print(" XXX - Getting Alarm Run Time  --- ERROR --- : {}".format(E))


def format_time(seconds):
    # Calculate days, hours, minutes, and seconds
    days = seconds // (24 * 3600)
    hours = (seconds % (24 * 3600)) // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    # Format the result
    time_str = f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
    return time_str



def get_fan_run_time():
    try:
        if FAN_STATUS and FAN_START_TIME != 0:
            cur_time = time.time()
            delta_time = cur_time - FAN_START_TIME
            print(" XXX - Getting Fan Run Time |  Delta Time--- " + str(delta_time))
            return delta_time
        else:
            return 0
    except Exception as e:
        print(f" XXX - Getting Alarm Run Time  --- ERROR --- : {e}")


def Exhaust_System():
    #turn fan on
    global FAN_STATUS, FAN_START_TIME
    FAN_START_TIME = time.time()
    FAN_STATUS = True
    Fan_OUTPUT.value(1)


def UNRENT_TRAILER():
    global RENT_STATUS
    try:
        print(" -- UN-RENT Trailer -- ")
        # Lock Hitch
        lock_trailer(1, True)
        RENT_STATUS = False
        return 0
    except Exception as e:
        print(f" -- UN-RENT Trailer -- Error: {e}")
        return 1

def CORRAL_UPDATE_INFO(payload_data):
    global CORAL_ADDR, CORAL_RAD, CORAL_LAT, CORAL_LON, CORAL_NAME
    try:
        coral_parts = payload_data.split("|")
        if len(coral_parts) >= 5:
            CORAL_NAME = str(coral_parts[0])
            CORAL_LAT = float(coral_parts[1])  # Potential ValueError
            CORAL_LON = float(coral_parts[2])  # Potential ValueError
            CORAL_RAD = float(coral_parts[3])  # Potential ValueError
            CORAL_ADDR = str(coral_parts[4])
            print(" -- | Coral Info Received: Name: {}, Address: {}, Radius: {} ft, Lat: {}, Lon: {}".format(
                    CORAL_NAME, CORAL_ADDR, CORAL_RAD, CORAL_LAT, CORAL_LON))
        else:
            print(f" XX MQTT - CORAL: (expected 5 parts): ({payload_data})", end="")
    except Exception as e:
        print(f" -- Coral Update Info Error: {e}")

def maintenance_update(payload_data):
    global MAINTENANCE_MODE
    if payload_data == "1":
       MAINTENANCE_MODE = True
       print(" -- Entering Maintenance Mode.  Disarming Alarm")
       if ALARM_STATUS: alarm(ALARM_CMD_OFF,"Entering Maintenance mode and Disarming Alarm")  # Use constant
       alarm(ALARM_CMD_OFF, "MTC ALARMOFF")  # Use constant
       beep(3, .2)
    elif payload_data == "0":  # Use elif for mutually exclusive conditions
       MAINTENANCE_MODE = False
       print(" -- Exiting Maintenance Mode.  ")
       beep(2, 1)


def sub_cb(topic, msg):
    try:
        global GONOW, GONOW_MSG, RENT_STATUS, ALARM_DURATION

        decoded_msg = msg.decode("utf-8")  # Decode once
        parts = decoded_msg.split(":", 2)  # Split max 2 times for commands like MTC:1 or CORAL:data
        if len(parts) >= 2:
            cmd = parts[0]
            request = parts[1]
            payload_data = parts[2] if len(parts) > 2 else None

            if cmd == "TCMD":
                print(f"  >> TCMD:{request}", end="")
                if request == 'MTC':
                    if payload_data in ("0", "1"):
                        maintenance_update(payload_data)
                    else:
                        print(f" XX MQTT - MTC: INVALID STATUS: ({payload_data})", end="")
                elif request == "UNLOCK":
                    lock_trailer(LOCK_CMD_UNLOCK, True)  # Use constant
                elif request == "LOCK":
                    lock_trailer(LOCK_CMD_LOCK, True)  # Use constant
                elif request == 'SHUTDOWN':
                    beep(4, SIREN_PULSE)
                    network.Cellular().shutdown(reset=False)
                elif request == 'REBOOT':
                    beep(3, SIREN_PULSE)
                    network.Cellular().shutdown(reset=True)
                    xbee.atcmd("FR")
                elif request == "BEEP":
                    beep(4, .25)
                elif request == "UPDATE":
                    GONOW = True
                    GONOW_MSG = "UPDATE"
                elif request == 'STATUS':
                    GONOW = True
                    GONOW_MSG = "TCMD RECEIVED: STATUS"
                elif request == 'EXHAUST':
                    GONOW = True
                    GONOW_MSG = "TCMD RECEIVED: EXHAUST"
                    beep(3, .2)
                    Exhaust_System()
                elif request == 'RENTED':
                    print(" -- TCMD: RENTED: Open For Business")
                    RENT_STATUS = True
                    if ALARM_STATUS: alarm(ALARM_CMD_OFF, "Disarm | Rental is Active")  # Use constant
                elif request == 'NOTRENTED':
                    print(" -- TCMD: NOTRENTED: SECURING TRAILER |")
                    UNRENT_TRAILER()
                elif request == "CORAL":
                    if payload_data:
                        CORRAL_UPDATE_INFO(payload_data)
                    else:
                        print(" XX MQTT - CORAL: MISSING DATA", end="")
                else:
                    print(" XX MQTT - TCMD: UNKNOWN:(" + str(request) + ")", end="")

    except Exception as e:
        print(f" XX  :(  Exception in sub_cb: \nERR: {e}")  # Added newline for error readability
    print(" << :) Processed Incoming Msg Attempt")  # Clarify it's an attempt


def publish_message(client, topic, message):
    print(" -- Publishing message... ", end="")
    pub_stat = client.publish(topic, message)
    print(" <<:) PUBLISHED : " + str(pub_stat))




############################################################################################
############### MAIN ROUTINE ###############################################################
############################################################################################

def Main_Routine(conn, ip, dns, phone_no,modem, apn, imei, iccid, freq, mport=SVR_PORT, hostname=SERVER, topic=TOPIC,
                 blocking=True):

    global GONOW, GONOW_MSG, LOCK_STATUS, LAST_STATUS, RENT_STATUS, ALARM_STATUS, ALARM_ACTIVATED_TIME, \
        MAINTENANCE_MODE, TOOLBOX_STATE, FAN_STATUS, FAN_START_TIME, ALARM_REPORT, START_ROUTINE, ALARM_DURATION, hdop_msg, \
        START_TIME_MainRoutine, START_TIME_SubRoutine
    def get_size(s):
        return len(s.encode('utf-8'))

    print("")
    print(" --------------------- Starting Main Routine  -----------------------------------")
    print(" |                                                                              |")
    print(" | Initialize Main Routine. ", end="")
    xb = xbee.XBee()
    print(" | XBEE initialized ", end="")
    gps = moo_serial()
    print(" | GPS initialized ", end="")
    # sat = moo_sats()
    # print(" | SATS initialized ")
    GPS_PRESENT = gps.test_gps()
    print("  -- GPS DATA FOUND") if GPS_PRESENT else print("  -- GPS DATA NOT FOUND")

    # LOCK up Trailer
    lock_trailer(LOCK_CMD_LOCK, False)
    #### Connect TO MQTT Server ##########################################################################
    print(" |---- : mqtt Starting  Connection to '%s'... " % hostname)
    client = MQTTClient(client_id=phone_no, server=hostname, port=mport, user=phone_no, password=imei, ssl=False)
    client.set_callback(sub_cb)
    print(" |---- : mqtt Connecting to '%s'... " % hostname)
    client.connect()
    print(" |---- : Subscribing to topic '%s'... " % topic, end="")
    client.subscribe(topic)
    print(" *** CONNECTED ***")

    #### GET INITIAL GPS DATA  ############################################################################
    gps_data = ""
    if GPS_PRESENT:
        try:
            gps_data = gps.read_gps()
        except:
            print(" -- GPS FAILED TO READ")

    #network_info = ('{"command":"status", "phone":"' + phone_no + '","ip":"' + ip + '","dns":"' +
    #                dns + '","imei":"' + imei + '","iccid":"' + iccid + '","freq":"' + freq + '","motion":"0",}')

    network_info_dict = {
        "command": "status", "phone": phone_no, "ip": ip, "dns": dns,
        "imei": imei, "iccid": iccid, "freq": freq, "motion": "0"
    }

    ##### Display phone and GPS data  ######################################################################
    print(" |---- : Cellular Data ---------------------------------")
    print(f" |---- : Phone Number is : {phone_no}")
    print(f" |---- : IP Address is   : {ip}")
    print(f" |---- : DNS Address is  : {dns}")
    print(f" |---- : IMEI is         : {imei}")
    print(f" |---- : ICCID is        : {iccid}")
    print(f" |---- : Freq Ch is      : {freq}")
    print(" |---- : Json Data ---------------------------------------")
    print(f" |---- : Network Json    : {network_info_dict}")
    if GPS_PRESENT:
        print(f" |---- : GPS Data        : {gps_data}")
    else:
        print(" |!!!! : NO GPS FOUND    : ")
    print(" |----------------------------------------------------")
    print(" |                                                                              |")
    print(" |------------------------------------------------------------------------------|")
    print("")

    #go_data = json.loads(network_info)
    go_data = network_info_dict.copy()
    go_data.update(conn.signal())

    # send initial GPS and CELL data
    if GPS_PRESENT and len(str(gps_data)) > 45: go_data.update(json.loads(gps_data))

    ## Retrieve Trailer Information
    publish_message(client, topic, json.dumps({"command": "rent_status"}))
    publish_message(client, topic, json.dumps({"command": "coral_info"}))
    publish_message(client, topic, json.dumps({"command": "mtc_status"}))
    client.check_msg()

    # Main Routine initial variables   -----------------------------------------------
    cntr = 0
    main_loop_timer = 20  # main loop runs every x for events
    main_loop_timer_cnt = 0

    LOCK_STATE = LOCK_NOTICE.value()
    PLUGGED_STATE = PLUGGED_HOT.value()
    TOOLBOX_STATE = TOOLBOX_TRIGGER.value()  # Initialized global TOOLBOX_STATE is 2, this localizes it
    STARTUP = True

    gc.collect()

    def check_connection():
        # Testing MQTT Connection
        if client.is_mqtt_connected():
            return True
        else:
            attempts = 1
            while client.is_mqtt_connected() is False:
                try:
                    time.sleep(5 * attempts)
                    client.connect()
                    client.subscribe(topic)
                    print(" !! RECOVERED MQTT CONNECTION")
                except:
                    attempts += 1
                    print(" XX MQTT CONNECTION FAILED")
                    if conn.isconnected() is False:
                        print(" XX NO CELLULAR CONNECTION")
                    else:
                        print(" !! CELLULAR CONNECTED")
                    if attempts >= 12: attempts = 12
        return True


    def cell_string():
        try:
            signal_data = conn.signal()
            cs = signal_data.copy()
            rssi = cs["rssi"]
            rsrp = cs["rsrp"]
            rsrq = cs["rsrq"]

            print(f" -- Cellular Status: RSSI (Power): {rssi}/ ", end="")
            if rssi >= -65:
                print("Excellent" ,end="")
            elif rssi >= -75:
                print("Good",end="")
            elif rssi >= -85:
                print("Fair",end="")
            elif rssi >= -99:
                print("Poor",end="")
            else:
                print("Deficient",end="")

            print(f" | RSRP (Reference Signal): {rsrp}/ ", end="")
            if rsrp >= -80:
                print("Excellent",end="")
            elif rsrp >= -90:
                print("Good",end="")
            elif rsrp >= -110:
                print("Fair",end="")
            else:
                print("Deficient",end="")

            print(f" | RSRQ (Quality): {rsrq}/ ", end="")
            if rsrq >= -10:
                print("Excellent")
            elif rsrq >= -15:
                print("Good")
            elif rsrq >= -20:
                print("Fair")
            else:
                print("Poor")

        except Exception as e:
            print(f" -- Cellular Status: RSSI (Power):  FAILED TO retrieve cell signal: {e}")

    print("/n<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< STARTING MAIN WHILE LOOP >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>/n")
    START_TIME_SubRoutine = timestamp()
    while xb.wake_lock:
        try:
                global SCRIPT_EPOCH_START_TIME  # Ensure this is the global one
                if START_ROUTINE and (time.time() - SCRIPT_EPOCH_START_TIME > START_ROUTINE_Time):
                    print(f" -- Startup routine time ({START_ROUTINE_Time}s) elapsed. Enabling beeps.")
                    START_ROUTINE = False
                gc.collect()

                try:
                    client.check_msg()
                except:
                    check_connection()
                    client.check_msg()

                # Send Alarm notifications to Cloud for processing.
                if ALARM_REPORT != 0:
                    if ALARM_REPORT == 1:
                        print(" !! ALARM | Sending ACTIVE Notification ")
                        event_id = phone_no + "-" + str(int(time.time()))
                        alarm_payload = {"command":"ALARM","msg":ALARM_MSG,"event_id":event_id}
                        try:
                            publish_message(client, topic, json.dumps(alarm_payload))
                        except:
                            check_connection()
                            publish_message(client, topic, json.dumps(alarm_payload))

                        del alarm_payload, event_id
                        ALARM_REPORT = 0
                    if ALARM_REPORT == 2:
                        print(" !! UNALARM | Sending NON-ACTIVE Notification ")
                        event_id = phone_no + "-" + str(int(time.time()))
                        alarm_msg = f'"command":"UNALARM","msg":"{ALARM_MSG}","event_id":"{event_id}"'
                        alarm_msg = json.loads('{' + alarm_msg + '}')
                        try:
                            publish_message(client, topic, json.dumps(alarm_msg))
                        except:
                            check_connection()
                            publish_message(client, topic, json.dumps(alarm_msg))
                        del alarm_msg, event_id
                        ALARM_REPORT = 0

                ### ALARM ---- Counts Down Alarm
                if ALARM_STATUS and (STARTUP is False):
                    print(
                        f" !! ***** ALARM STATUS : {ALARM_STATUS} | Maintenance Mode: {MAINTENANCE_MODE} | Rent Status: {RENT_STATUS}")
                    gart = get_alarm_run_time()  # returns in seconds how long alarm has been active
                    print(f" !! ALARM DURATION {gart} seconds ")
                    if gart > ALARM_DURATION:  # Turn off alarm if exceeds Alarm Duration
                        print(" !! ***** ALARM exceeded Duration : DISARM alarm ")
                        alarm(ALARM_CMD_OFF, "Disarm, Exceed Alarm Duration")
                    else:  # Keep Alarming --- has not timed out.
                        print(" !! ***** ALARM Time remaining {} seconds ".format(str(ALARM_DURATION - gart)))
                    del gart

                ## FAN STATUS Count Down #######################
                if FAN_STATUS and (STARTUP is False):
                    print(" !! *******  FAN is Runnning: ", end="")
                    fart = get_fan_run_time()
                    if fart > FAN_RUNTIME:  # Turn Fan Off
                        FAN_START_TIME = 0
                        FAN_STATUS = False
                        Fan_OUTPUT.value(0)
                        print(" !! Stopping Fan.")
                    else:
                        print("")
                    del fart

                gc.collect()

                #### Check GPIO events #######################################################
                ### TOOLBOX is opened and trigger alarm
                current_toolbox_value = TOOLBOX_TRIGGER.value()
                if current_toolbox_value != TOOLBOX_STATE:
                    if STARTUP is False and START_ROUTINE is False:
                        if current_toolbox_value == 0:
                            GONOW = True
                            GONOW_MSG = "Toolbox OPENED"
                            print(f"  !!  {GONOW_MSG} !!")
                            ALARM_DURATION = 90
                            alarm(ALARM_CMD_ON, GONOW_MSG)
                        else:
                            GONOW = True
                            GONOW_MSG = "Toolbox CLOSED"
                            print(f"  !!  {GONOW_MSG} !!")
                            alarm(ALARM_CMD_OFF, GONOW_MSG)
                    TOOLBOX_STATE = current_toolbox_value
                del current_toolbox_value

                if TOOLBOX_STATE == 0 and ALARM_STATUS is False and STARTUP is False and RENT_STATUS is False:  #Toolbox is OPEN
                    ALARM_DURATION = 180
                    alarm(ALARM_CMD_ON, "TOOLBOX OPENED")

                current_NOTICE_lock_val = LOCK_NOTICE.value()
                if current_NOTICE_lock_val != LOCK_STATE:
                    if STARTUP is False and START_ROUTINE is False:
                        GONOW = True
                        if current_NOTICE_lock_val == 0:
                            GONOW_MSG = "LOCK STATE CHANGED: LOCKED"
                        else:
                            GONOW_MSG = "LOCK STATE CHANGED: UNLOCKED"
                        print(f" !! {GONOW_MSG}")
                    LOCK_STATE = current_NOTICE_lock_val
                del current_NOTICE_lock_val

                current_plug_status = PLUGGED_HOT.value()
                if current_plug_status != PLUGGED_STATE:
                    time.sleep(1)  # wait a second to make sure status hasn't changed in a minute
                    current_plug_status = PLUGGED_HOT.value()
                    if current_plug_status != PLUGGED_STATE:
                        if STARTUP is False and START_ROUTINE is False:
                            GONOW = True
                            if current_plug_status == 0:
                                GONOW_MSG = " ++ Trailer IS NOT Plugged into vehicle: COLD"
                                alarm(ALARM_CMD_OFF, GONOW_MSG + " | De-activating Alarm")
                            else:
                                GONOW_MSG = " ++ Trailer IS Plugged into vehicle: HOT"
                                dynamic_reporting(100)
                                if RENT_STATUS is False:
                                    ALARM_DURATION = 30
                                    alarm(ALARM_CMD_ON, GONOW_MSG + " and not Rented | Alarm Activated | {}  status".format(RENT_STATUS))
                            print(f" !! Plug Status : {GONOW_MSG}")
                        PLUGGED_STATE = current_plug_status
                if PLUGGED_STATE != 0 and ALARM_STATUS is False and STARTUP is False and RENT_STATUS is False:  #plugged and hot
                    ALARM_DURATION = 180
                    alarm(ALARM_CMD_ON, " ++ Trailer IS Plugged into vehicle: HOT and not Rented")
                del current_plug_status

                #### END of Listening for GPIO events --------------------------------

                if STARTUP:
                    GONOW = True
                    GONOW_MSG = "STARTUP"

                if True:
                    if main_loop_timer_cnt >= main_loop_timer or GONOW:
                        ### Check of GPS is onine
                        gd = True
                        while gd:
                            try:
                                if GPS_PRESENT is False: GPS_PRESENT = gps.test_gps()
                                main_loop_timer_cnt = 0
                                if GONOW_MSG == "UPDATE":
                                    publish_message(client, topic, '{"command":"rent_status"}')
                                    publish_message(client, topic, '{"command":"coral_info"}')
                                    publish_message(client, topic, '{"command":"mtc_status"}')
                                if GONOW_MSG == "RESETDATA":
                                    publish_message(client, topic, '{"command":"resetdata"}')

                                #go_data = json.loads(network_info)
                                go_data = network_info_dict.copy()
                                go_data.update({"build_no": BUILD_NO, "build_date": BUILD_DATE})
                                go_data.update(conn.signal())
                                go_data["cell_strength"] = get_cell_strength()
                                gd = False
                            except:
                                print(" XX 234C PUBLISH DATA FAILED TRY Again. Checking Connection")
                                check_connection()
                        del gd
                        gc.collect()

                        #Load GPS data
                        if GPS_PRESENT:
                            gps_data = gps.read_gps()
                            gc.collect()
                            GPS_GOOD = False

                            if len(str(gps_data)) > 45:
                                print(f" -- GPS has a FIX: ANTENNA is {gps.gps_ant}: ", end="")
                                sats = float(gps.get_sats())
                                hdop = float(gps.get_hdop())
                                hdop_msg = "na"
                                print(f" hdop: {hdop} sats: {sats}")

                                if hdop == 0:
                                    print(" !!!! Bad Satellite Read")
                                elif hdop < 1.0 and sats > 10:
                                    GPS_GOOD = True
                                    hdop_msg = "STRONG"
                                elif hdop < 2 and sats > 6:
                                    GPS_GOOD = True
                                    hdop_msg = "FAIR"
                                elif hdop  < 8 and sats > 3:
                                    GPS_GOOD = True
                                    hdop_msg = "Moderate"
                                else:
                                    print(f" !!!! WEAK signal !!!! hdop: {hdop} sats: {sats}")

                                if GPS_GOOD:
                                    clat, clon = gps.get_current_latlon()
                                    print(f"    >> {hdop_msg} signal hdop: {hdop} sats: {sats} lat: {clat} lon: {clon}", end="")
                                    del clat, clon

                                    try:
                                        go_data.update(json.loads(gps_data))
                                    except:
                                        print(f"  -- GPS FAIL Failed to load GPS JSON: {gps_data}")
                                    try:
                                        go_data["gps_antenna"] = gps.gps_ant
                                    except :
                                        print(f"  -- GPS FAIL ANTENNA to load GPS JSON: {gps.gps_ant}")

                                del hdop, sats

                            else:
                                print(f" XX -- GPS ANTENNA is {gps.gps_ant}")
                                print(f" XX -- GPS ERROR 412--: {gps_data}")

                            del gps_data
                            gc.collect()
                            print(f" ****  GPS data is : {GPS_GOOD}")
                            if GPS_GOOD == True:
                                if hdop_msg == "STRONG" or hdop_msg == "FAIR":
                                    gps_speed = gps.get_current_speed()
                                    gps_distance = gps.get_distance()
                                    print(f"    >> Checking Speed and Distance speed {gps_speed}: Distance Traveled: {gps_distance} ft")
                                    if gps_speed > 15 and gps_distance > 450:
                                        print("   >> Trailer in motion: ")
                                        if LOCK_STATE != 0:
                                            print(f"      Trailer Not locked while in motion |  LOCKING TRAILER |  STATUS: {LOCK_STATE}", end="")
                                            lock_trailer(1,False)
                                            print(f" UPDATED STATUS: {LOCK_STATE}")
                                        if not RENT_STATUS:
                                            print("  !!WARNING!! ---- Trailer in motion and not Rented moving @: {}mph".format(
                                                gps_speed))
                                            alarm(1, "Trailer In Motion and not Rented")

                                    del gps_speed, gps_distance
                                    gc.collect()
                                    # Has Trailer Left Coral
                                    if CORAL_LON != "" and CORAL_LAT != "":
                                        gps_distance_from_coral = int(gps.gps_dif_distance(CORAL_LAT, CORAL_LON))
                                        print(f"    >> Coral Distance is {gps_distance_from_coral} ft", end="")
                                        go_data["coral_distance"] = gps_distance_from_coral
                                        print(f" | ", end="")

                                        if gps_distance_from_coral > float(CORAL_RAD):
                                            print(f" !! | ", end="")
                                            coral_held = 0
                                            print(" | OUT of Coral", end="")
                                            if MAINTENANCE_MODE is False and RENT_STATUS is False:
                                                print(" | Second Corral Check ", end="")  # Double Check
                                                time.sleep(5)
                                                gps_data2 = gps.read_gps()
                                                hdop = float(gps.get_hdop())
                                                sats = float(gps.get_sats())
                                                if len(str(gps_data2)) > 45 and hdop < 2 and sats > 5:
                                                    if int(gps.gps_dif_distance(CORAL_LAT, CORAL_LON)) > float(CORAL_RAD):
                                                        print(
                                                            f" 2nd CHECK Confirmed | ACTIVATING ALARM Maintenance Mode {MAINTENANCE_MODE} or Rent Status {RENT_STATUS} is negative")
                                                        ALARM_DURATION = 90
                                                        alarm(1, "Trailer has left coral. Activating Alarm")
                                                    else:
                                                        print("  -- 2nd Check Failed. Trailer in Corral")
                                                del gps_data2, hdop, sats
                                        else:
                                            coral_held = 1
                                            if ALARM_STATUS and TOOLBOX_TRIGGER.value() != 0 and PLUGGED_HOT.value() == 0:  # Tool box is closed and not plugged into car
                                                alarm(2,
                                                      "Trailer ENTERED corral. DE-Activating Alarm, toolbox is closed and not plugged into vehicle")
                                                print(
                                                    " | DISARMING ALARM |  IN CORAL - Toolbox is Closed - Not Plugged into vehicle ",
                                                    end="")
                                            print(" | IN Coral", end="")
                                        go_data["coral_held"] = coral_held
                                        go_data["coral"] = CORAL_NAME
                                        go_data["coral_radius"] = CORAL_RAD
                                        print(" <<  CORAL DONE")
                                        del gps_distance_from_coral, coral_held
                                    else:
                                        print(" -- NO CORRAL INFO: requesting corral info")
                                        publish_message(client, topic, '{"command":"coral_info"}')
                            else:
                                #GPS DATA is BAD....
                                pass

                        # Load Lock State
                        LOCK_STATUS = "LOCKED" if LOCK_NOTICE.value() == 0 else "UNLOCKED"
                        go_data["lock_status"] = LOCK_STATUS
                        print(f" -- Lock State: {LOCK_STATUS}", end="")

                        # Load Plug status
                        PLUG_STATUS = "HOT" if PLUGGED_HOT.value() == 1 else "COLD"
                        go_data["plugged"] = PLUG_STATUS
                        print(f" | Plug Status: {PLUG_STATUS}", end="")
                        del PLUG_STATUS

                        # Load TOOLBOX OPEN or CLOSED
                        TOOLBOX_STATUS = "OPEN" if TOOLBOX_TRIGGER.value() == 0 else "CLOSED"
                        go_data["toolbox"] = TOOLBOX_STATUS
                        print(f" | Toolbox Status: {TOOLBOX_STATUS} |")
                        del TOOLBOX_STATUS

                        # Load alarm status
                        go_data["alarm"] = str(ALARM_STATUS)

                        # Load modem temperature data
                        modem_temp = get_temp()
                        go_data["temp_modem"] = modem_temp


                        ### Exhaust Heat CHECK
                        print(f" -- Modem Heat Check | {modem_temp}", end="")
                        if modem_temp > FAN_THRESHOLD:
                            print(f" | Heat above {FAN_THRESHOLD} | exhausting heat")
                            Exhaust_System()
                        else:
                            print(f" | Heat below {FAN_THRESHOLD} | Normal Operating Temp")

                        # Siren STATUS
                        if SIREN_TRAILER.value() == 1:
                            print(f" -- Siren status: {SIREN_TRAILER.value()}  !!!! ACTIVE !!!!")
                        else:
                            print(f" -- Siren status: {SIREN_TRAILER.value()}  ... not active ...")

                        fanv = "Running" if FAN_STATUS else "Stopped"
                        go_data["fan"] = fanv
                        del modem_temp, fanv

                        # Load Start Data
                        go_data["started"] = START_TIME
                        go_data["started_main"] = START_TIME_MainRoutine
                        go_data["started_sub"] = START_TIME_SubRoutine


                        # Adjust reporting Frequency and load new freduency data
                        if PLUGGED_HOT.value() != 0:
                            # if PLUGGED into vehicle. REPORT MAX
                            go_data["reporting_freq"] = dynamic_reporting(100)
                        else:
                            if GPS_PRESENT:
                                go_data["reporting_freq"] = dynamic_reporting(gps.current_speed)

                        go_data["online"] = 1
                        go_data["error_last_msg"] = LAST_ERR_MSG


                        # I2C sensors  ----------------------------------------------------------------------------------
                        # Load ambient temperature data from I2C bus
                        go_data["pwr_volt"] = sensors.voltage()
                        go_data["pwr_current"] = sensors.current()
                        go_data["pwr_power"] = sensors.power()
                        go_data["temp_ambi"] = sensors.temperature()
                        print(f" -- Power Check | Volt:{go_data['pwr_volt']} Curr:{go_data['pwr_current']} Pwr:{go_data['pwr_power']} Temp:{go_data['temp_ambi']}")
                        ###  End of I2C Sensors ___________________________________________________________________________

                        go_data["GONOW"] = "TRIGGERED" if GONOW else "NOT TRIGGERED"
                        go_data["GONOW_MSG"] = GONOW_MSG

                        if GONOW: print(f" -- GONOW_MSG: {GONOW_MSG}")
                        # END GO NOW Status --------------------------------------------------------------------------------

                        # Json data Size
                        go_data["size"] = get_size(str(go_data))
                        # Device ID
                        go_data["device"] = modem
                        go_data["apn"] = apn

                        ## Clean and Report memory usage
                        gc.collect()
                        cur_perc_mem = int((gc.mem_alloc() / 64000) * 100)
                        print(" -- MEMORY Usage:{}% ".format(cur_perc_mem), )
                        go_data["memory_pct "] = cur_perc_mem
                        del cur_perc_mem

                        # Send Data to Firebase
                        print("------------------------------------------------------------------------------------------------")
                        if cntr >= Run_Time or GONOW:
                            print(" -- SENDING DATA to Mothership ...... : " + str(get_current_time()))
                            if GONOW:
                                print(" -- GO NOW ACTIVATED")
                            else:
                                print(" -- Timer ACTIVATED")

                            GONOW = False
                            GONOW_MSG = ""
                            cntr = 0
                            try:
                                publish_message(client, topic, str(go_data))
                            except Exception as e:
                                print(" XX 456CC Failed to send Firebase Data: Checking Connection")
                                check_connection()
                                publish_message(client, topic, str(go_data))

                            del go_data
                        else:
                            print(f" -- Counter: {cntr}/{Run_Time}")
                            cell_string()

                    ### END of LOOP #################
                    cntr = cntr + 1
                    main_loop_timer_cnt = main_loop_timer_cnt + 1
                    time.sleep(1)
                    STARTUP = False
        except Exception as e:
            print("")
            print(" ---------------------------------------------------------")
            print(" *****  main WHILE Failed : " + str(e))
            print(" *****  Restarting While Loop ")
            print(" ---------------------------------------------------------")
            check_connection()



########################################################################################
####                         Start of program                                       ####
########################################################################################
while True:
    try:
        START_TIME = timestamp()
        START_TIME_RAW = time.time()
        conn = network.Cellular()
        LAST_ERR_MSG = ""

        if 'err.txt' in os.listdir('.'):
            print(" XX Err File Found : ", end="")
            try:
                with open('err.txt') as f:
                    print(f.read(), end="")
            except Exception as e:
                print(f"[Error reading file: {e}]")

        ###### Starting Routine  ##################################################
        print(" +------------------------------------------------+")
        print(" |  Moovalot | Xbee Communications Python Script  |")
        print(" +------------------------------------------------+\n")
        print(" ---- : Waiting for the module to be connected to the cellular network... ")
        while not conn.isconnected(): time.sleep(5)
        print(" ---- : Cell info : Is Connected : " + str(conn.isconnected()))
        print(" ---- : Cell info : Phone No     : " + str(xbee.atcmd("PH")))
        print(" ---- : Cell info : Signal       : " + str(conn.signal()))
        print(" ---- : Cell info : ifconfig     : " + str(conn.ifconfig()))
        print(" ---- : Cell info : scan         : " + str(conn.scan()))
        print(" ---- : Cell info : modem temp   : " + str(get_temp()))
        print(" ---- : Starting Time            : " + timestamp() + "|")

        phone_number = xbee.atcmd("PH")

        phone_number = str(phone_number).replace("+", "")
        print(" ---- : starting Main Routine    : Phone : " + phone_number)
        try:
           #### Start Up Routine
          START_TIME_MainRoutine = timestamp()
          Main_Routine(conn,
                     ip=conn.ifconfig()[0],
                     dns=conn.ifconfig()[3],
                     phone_no=phone_number,
                     modem = xbee.atcmd("HS"),
                     apn=xbee.atcmd("AN"),
                     imei=xbee.atcmd("IM"),
                     iccid=xbee.atcmd("S#"),
                     topic=TOPIC + phone_number,
                     freq=str(xbee.atcmd("FC")),
                     blocking=False)
        except Exception as E:
            print("")
            print(" ---------------------------------------------------------")
            print(" *****  main Routine  Failed : " + str(E))
            print(" *****  Restarting")
            print(" ---------------------------------------------------------")
            err_msg = str(E).replace("'", " ").replace(",", "")

    except Exception as E:
        print("")
        print(" ********************************************************")
        print(" *****  Cellular Connection  Failed : " + str(E))
        print(" *****  Restarting")
        print(" *********************************************************")
        err_msg = str(E).replace("'", " ").replace(",", "")

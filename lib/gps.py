import time
from machine import UART

class moo_serial:
    def __init__(self):
        self.current_speed = 0.0
        self.p_lat = 0.0
        self.p_lon = 0.0
        self.p_distance = 0.0
        self.TMZ = -5
        self.FIX = False
        self.LON_MAX = -71
        self.LON_MIN = -125
        self.LAT_MAX = 50
        self.LAT_MIN = 24
        self.HDOP = 0.0
        self.SATS = 0
        self.gps_time = ""
        self.gps_date = ""
        self.gps_lat = ""
        self.gps_lon = ""
        self.gps_bearing = ""
        self.gps_speed = ""
        self.gps_rw_time = ""
        self.gps_rw_status = ""
        self.gps_rw_dt = ""
        self.gps_alt = ""
        self.gps_ant = "DOWN"
        self.u = None

    def read_gps(self):
        try:
            if self.u is not None:
                self.reset_gps_UART()
            self.u = UART(1, 9600)
            self.u.init(9600, bits=8, parity=None, stop=1)
            result = False
            raw_gps_data = ""
            self._clear_gps_data()
            cntr = 0
            wait_time = 0.5
            total_time = 10
            calc_waittime = total_time / wait_time
            while True:
                d = self.u.read()
                if d:
                    raw_gps_data = "start\n" + str(d, 'utf8')
                    if "$GNRMC" in raw_gps_data or "$GPRMC" in raw_gps_data:
                        if self._extract_RMC(raw_gps_data) == "0":
                            if self._GPS_DATA_CHECK():
                                result = True
                    if "$GNGGA" in raw_gps_data and result is False:
                        if self._extract_GGA(raw_gps_data) == "0":
                            if self._GPS_DATA_CHECK():
                                result = True
                    if "ANTENNA" in raw_gps_data:
                        try:
                            x = raw_gps_data.split("ANTENNA", 1)[1].split("*")[0].strip()
                            self.gps_ant = x
                        except:
                            pass
                    del d
                if result:
                    break
                else:
                    time.sleep(wait_time)
                    cntr += 1
                    if cntr >= calc_waittime:
                        break
            if result:
                if self.LAT_MIN < float(self.gps_lat) < self.LAT_MAX and self.LON_MIN < float(self.gps_lon) < self.LON_MAX:
                    try:
                        if self.p_lat == 0.0:
                            self.p_distance = 0
                        else:
                            self.p_distance = self._gps_distance((self.gps_lat, self.gps_lon), (self.p_lat, self.p_lon))
                    except:
                        self.p_distance = 0
                    self.p_lat = self.gps_lat
                    self.p_lon = self.gps_lon
                    self.u.deinit()
                    return self._gps_string_Data()
                else:
                    self.u.deinit()
                    return "6| GPS Garbage Data Extracted"
            else:
                self.u.deinit()
                return "7|No Valid GPS Data"
        except Exception as e:
            if self.u is not None:
                try:
                    self.u.deinit()
                except:
                    pass
                self.u = None
            return "6|GPS Error (gps.py):>>" + str(e) + "<< Rawdata:"

    def get_current_latlon(self):
        return self.p_lat, self.p_lon

    def reset_gps_UART(self):
        try:
            if self.u is not None:
                self.u.deinit()
            self.u = None
            return True
        except:
            self.u = None
            return False

    def test_gps(self):
        try:
            print("GPS abc")
            if self.u is not None:
                self.reset_gps_UART()
            self.u = UART(1, 9600)
            self.u.init(9600, bits=8, parity=None, stop=1)
            time.sleep(1)
            raw_gps_data = str(self.u.read(), 'utf8')
            self.u.deinit()
            self.u = None
            return len(raw_gps_data) > 5
        except:
            return False

    def get_current_speed(self):
        try:
            return float(self.current_speed)
        except:
            return 0

    def get_distance(self):
        try:
            return float(self.p_distance)
        except:
            return 0

    def _clear_gps_data(self):
        self.HDOP = 0.0
        self.SATS = 0
        self.gps_time = ""
        self.gps_date = ""
        self.gps_lat = ""
        self.gps_lon = ""
        self.gps_bearing = ""
        self.gps_speed = ""
        self.gps_rw_time = ""
        self.gps_rw_status = ""
        self.gps_rw_dt = ""
        self.gps_alt = ""

    def _GPS_DATA_CHECK(self):
        return (
            self.HDOP != 0.0 and
            self.SATS != 0 and
            self.gps_time != "" and
            self.gps_date != "" and
            self.gps_lat != "" and
            self.gps_lon != "" and
            self.gps_bearing != "" and
            self.gps_speed != "" and
            self.gps_rw_time != "" and
            self.gps_rw_status != "" and
            self.gps_rw_dt != ""
        )

    def _extract_RMC(self, serial_data):
        try:
            RMC_MARK = "$GNRMC" if "$GNRMC" in serial_data else "$GPRMC"
            gn_rmc = serial_data.split(RMC_MARK, 1)
            parts = gn_rmc[1].split(",")
            if parts[2] != "A":
                return "7|NO FIX"
            if len(parts) < 9:
                return "9|less than 9 array"
            latitude = self._convertToDigree(parts[3])
            if parts[4] == 'S':
                latitude = "-" + latitude
            longitude = self._convertToDigree(parts[5])
            if parts[6] == 'W':
                longitude = "-" + longitude
            rate = self._converKnotstoMile(parts[7])
            bearing = parts[8]
            gps_time = parts[1][0:2] + ":" + parts[1][2:4] + ":" + parts[1][4:6]
            cur_date = parts[9][2:4] + "/" + parts[9][0:2] + "/" + parts[9][4:6]
            self.FIX = True
            self.current_speed = rate
            self.gps_time = gps_time
            self.gps_date = cur_date
            self.gps_lat = latitude
            self.gps_lon = longitude
            self.gps_bearing = bearing
            self.gps_speed = rate
            self.gps_rw_time = parts[1]
            self.gps_rw_status = parts[2]
            self.gps_rw_dt = parts[9]
            self.gps_rw_lat = parts[3]
            self.gps_rw_lat_d = parts[4]
            self.gps_rw_lon = parts[5]
            self.gps_rw_lon_d = parts[6]
            return "0"
        except Exception as e:
            return "3| Err RMC Data: " + str(e)

    def _extract_GGA(self, serial_data):
        try:
            RMC_MARK = "$GNGGA" if "$GNGGA" in serial_data else "$GPGGA"
            gn_rmc = serial_data.split(RMC_MARK, 1)
            parts = gn_rmc[1].split(",")
            if parts[6] == "0":
                return "7|NO FIX"
            if len(parts) < 9:
                return "9|less than 14 array"
            latitude = self._convertToDigree(parts[2])
            if parts[3] == 'S':
                latitude = "-" + latitude
            longitude = self._convertToDigree(parts[4])
            if parts[5] == 'W':
                longitude = "-" + longitude
            gps_time = parts[1][0:2] + ":" + parts[1][2:4] + ":" + parts[1][4:6]
            self.FIX = True
            self.gps_time = gps_time
            self.gps_lat = latitude
            self.gps_lon = longitude
            self.gps_rw_time = parts[1]
            self.SATS = parts[7]
            self.HDOP = float(parts[8])
            self.gps_rw_status = parts[6]
            self.gps_rw_lat = parts[2]
            self.gps_rw_lat_d = parts[3]
            self.gps_rw_lon = parts[4]
            self.gps_rw_lon_d = parts[5]
            self.gps_alt = parts[9]
            return "0"
        except Exception as e:
            return "3| Err GNGGA: " + str(e)

    def _convertToDigree(self, RawDegrees):
        RawAsFloat = float(RawDegrees)
        firstdigits = int(RawAsFloat / 100)
        nexttwodigits = RawAsFloat - float(firstdigits * 100)
        Converted = float(firstdigits + nexttwodigits / 60.0)
        return '{0:.6f}'.format(Converted)

    def _gps_string_Data(self):
        return '{"gps_time":"' + self.gps_time + \
               '","gps_date":"' + self.gps_date + \
               '","gps_lat":"' + self.gps_lat + \
               '","gps_lon":"' + self.gps_lon + \
               '","gps_bearing":"' + self.gps_bearing + \
               '","gps_speed":"' + self.gps_speed + \
               '","gps_rw_time":"' + self.gps_rw_time + \
               '","gps_rw_status":"' + self.gps_rw_status + \
               '","gps_rw_dt":"' + self.gps_rw_dt + \
               '","gps_sats":"' + str(self.SATS) + \
               '","gps_hdop":"' + str(self.HDOP) + \
               '","gps_alt":"' + str(self.gps_alt) + '"}'

    def _converKnotstoMile(self, knots):
        return str(round(float(knots) * 1.15078, 1))

    def _convertHrtoCST(self, hr):
        rawHr = int(hr)
        cstHr = rawHr + self.TMZ
        return "0" + str(cstHr) if cstHr < 10 else str(cstHr)

    def _radians(self, deg):
        pi = 3.14159265
        return deg * pi / 180

    def _sqr_rt(self, number):
        if number < 0:
            return 0
        guess = number / 2
        while True:
            new_guess = (guess + number / guess) / 2
            if abs(new_guess - guess) < 1e-10:
                return new_guess
            guess = new_guess

    def _gps_distance(self, coord1, coord2):
        try:
            lat1, lon1 = coord1
            lat2, lon2 = coord2
            raw_distance = self._sqr_rt(pow(float(lat2) - float(lat1), 2) + pow(float(lon2) - float(lon1), 2)) * 1000000
            conv_ratio = 98
            distance = ((raw_distance * conv_ratio) / 1000) * 3.281
            return distance
        except:
            return 0

    def _is_float(self, val):
        try:
            return isinstance(float(val), float)
        except:
            return False

    def gps_dif_distance(self, lat, lon):
        return self._gps_distance((lat, lon), (self.p_lat, self.p_lon))

    def get_hdop(self):
        return self.HDOP

    def get_sats(self):
        return self.SATS

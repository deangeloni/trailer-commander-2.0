from machine import I2C
import time, struct
from micropython import const

class i2c_sensors:

            def __init__(self):
                self.i2c = I2C(id=1, freq=400000)
                self.address = 0x40
                self.REG_CURRENT = 0x01
                self.REG_BUS_VOLTAGE = 0x02
                self.REG_POWER = 0x03
            def _read(self, reg):
                res = self.i2c.readfrom_mem(self.address, reg, 2)
                return bytearray(res)
            def temperature(self):
                try:
                    # Scan shows device at 0x19
                    self.i2c.writeto(const(0x18) , bytearray([const(5)]))
                    time.sleep(0.0635)
                    raw=self.i2c.readfrom(const(0x18) , const(5))
                    u = (raw[0] & 0x0f) << 4
                    l = raw[1] / 16
                    if raw[0] & 0x10 == 0x10:
                       temp = (u + l) - 256
                    else:
                        temp = u + l
                    return (temp *  9/5) + 32
                except Exception as E:
                    print(" *****  I2C Temp failed: " + str(E))
                    return 0
            def voltage(self):
                try:
                    voltage = struct.unpack('>H', self._read(self.REG_BUS_VOLTAGE))[0]
                    # b = bytearray(2)
                    # self.i2c.readfrom_mem_into(0x40, 0x02 & 0xff,  b)
                    # voltage = (b[0] << 8) + b[1]
                    voltage *= 0.00125  # 1.25mv/bit
                    return voltage
                except Exception as E:
                    print(" *****  I2C Volt failed: " + str(E))
                    return 0

            def current(self):
                try:
                    current1 = struct.unpack('>H', self._read(self.REG_CURRENT))[0]
                    if current1 & (1 << 15):
                        current1 -= 65535
                    current1 *= 0.00125  # 1.25mA/bit
                    return current1
                except Exception as E:
                    print(" *****  I2C Current failed: " + str(E))
                    return 0
            def power(self):
                try:
                    power1 = struct.unpack('>H', self._read(self.REG_POWER))[0]
                    power1 *= 0.01  # 10mW/bit
                    return power1
                except Exception as E:
                    print(" *****  I2C Power failed: " + str(E))
                    return 0

            def __del__(self):
                self.i2c.close()







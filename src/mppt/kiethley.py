#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : Jason Schultz
# Created Date: 2024-08-05
# version ='1.0'
# ---------------------------------------------------------------------------
"""a_short_module_description"""
# ---------------------------------------------------------------------------

from pymeasure.instruments.keithley import Keithley2400
import numpy as np
import pandas as pd
from time import sleep
import matplotlib.pyplot as plt
import os

area = 0.16  # cm^2
solar_power = 100  # mW/cm2
cell_name = "2024_11_06-03d"

path = f"./output/{cell_name}"
if not os.path.exists(path):
    os.makedirs(path)

GPIB_connection = "GPIB::24"
data_points = 140
averages = 10
max_voltage = 1.2
min_voltage = -0.2
voltage_sweep_time = 0.07

voltage = np.linspace(min_voltage, max_voltage, data_points)
voltage_reverse = np.linspace(max_voltage, min_voltage, data_points)
current = np.zeros_like(voltage)
current_reverse = np.zeros_like(voltage)
power = np.zeros_like(voltage)
power_reverse = np.zeros_like(voltage)

with Keithley2400(GPIB_connection) as keithley:
    print(keithley.id)
    keithley.reset()
    keithley.use_front_terminals()
    keithley.apply_voltage()
    keithley.measure_current()
    keithley.enable_source()

    print("JV Forward Sweep")
    for (i, v) in enumerate(voltage):
        keithley.config_buffer(averages)
        keithley.source_voltage = v
        keithley.start_buffer()
        keithley.wait_for_buffer()
        current[i] = keithley.mean_current*1000/area
        sleep(voltage_sweep_time)
    power = voltage*current

    sleep(1)
    print("JV Reverse Sweep")
    for (i, v) in enumerate(voltage_reverse):
        keithley.config_buffer(averages)
        keithley.source_voltage = v
        keithley.start_buffer()
        keithley.wait_for_buffer()
        current_reverse[i] = keithley.mean_current*1000/area
        sleep(voltage_sweep_time)
    power_reverse = voltage_reverse*current_reverse

data = pd.DataFrame({
    "Forward Voltage (V)": voltage,
    "Forward Current Density (mA/cm2)": current,
    "Forward Power Density (mW/cm2)": power,
    "Forward Efficiency (%)": power/solar_power * 100,
    "Reverse Voltage (V)": voltage_reverse,
    "Reverse Current Density (mA/cm2)": current_reverse,
    "Reverse Power Density (mW/cm2)": power_reverse,
    "Reverse Efficiency (%)": power_reverse/solar_power * 100
})
data.to_csv(f"{path}/data.csv")

plt.plot(voltage, current, label = "Forward")
plt.plot(voltage_reverse, current_reverse, label = "Reverse")
plt.xlabel("Voltage (V)")
plt.ylabel("Current Density ($mA/cm^2$)")
plt.legend()
plt.show()
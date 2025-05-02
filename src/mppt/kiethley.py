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
from numpy import ndarray
import pandas as pd
from time import sleep
import matplotlib.pyplot as plt
import os
from datetime import datetime


def JV_sweep(
        keithley: Keithley2400,
        voltage_start: float,
        voltage_end: float,
        data_points: int,
        sweep_time: float,
        area: float,
        averages: int = 5
) -> dict:
    voltage = np.linspace(voltage_start, voltage_end, data_points)
    current = np.zeros_like(voltage)

    for (i, v) in enumerate(voltage):
        keithley.config_buffer(averages)
        keithley.source_voltage = v
        keithley.start_buffer()
        keithley.wait_for_buffer()
        current[i] = keithley.mean_current
        sleep(sweep_time)

    resistance = voltage/current
    current_density = current*1000/area
    power_density = voltage*current_density
    data = {
        "Voltage (V)": voltage,
        "Current Density (mA/cm2)": current_density,
        "Power Density (mW/cm2)": power_density,
        "Resistance (Ohms)": resistance
    }
    return data


def determine_cell_parameters(
        voltage: ndarray,
        current_density: ndarray,
        power_density: ndarray,
        solar_power: float,
        direction: str
) -> pd.DataFrame:
    Jsc = np.interp(0, voltage, current_density)
    Voc = np.interp(0, current_density, voltage)
    print(Jsc)
    print(Voc)
    mpp_index = np.argmin(power_density)
    Vmpp = voltage[mpp_index]
    Jmpp = current_density[mpp_index]
    efficiency = power_density[mpp_index]*100/solar_power
    FF = Vmpp*Jmpp/(Voc*Jsc)
    t = datetime.now()
    print(Vmpp)
    print(Jmpp)
    print(efficiency)
    print(FF)

    data = pd.DataFrame({
        "Time": [t],
        "Direction": direction,
        "Efficiency (%)": [efficiency],
        "Fill Factor": [FF],
        "Vmpp (V)": [Vmpp],
        "Jmpp (mA/cm2)": [Jmpp],
        "Voc (V)": [Voc],
        "Jsc (mA/cm2)": [Jsc]
    })
    return data


area = 6  # cm^2
solar_power = 100  # mW/cm2
cell_name = "2025-03-14-Si-test5"

path = f"./output/{cell_name}"
if not os.path.exists(path):
    os.makedirs(path)

GPIB_connection = "GPIB::24"
data_points = 140
averages = 5
max_voltage = 0.8
min_voltage = -0.2
voltage_sweep_time = 0.07

voltage = np.linspace(min_voltage, max_voltage, data_points)
voltage_reverse = np.linspace(max_voltage, min_voltage, data_points)
current = np.zeros_like(voltage)
current_reverse = np.zeros_like(voltage)
resistance = np.zeros_like(voltage)
resistance_reverse = np.zeros_like(voltage)
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
        current[i] = keithley.mean_current
        sleep(voltage_sweep_time)
    resistance = voltage/current
    current = current*1000/area
    power = voltage*current
    dataf = determine_cell_parameters(voltage, current, power, solar_power, "Forward")
    dataf.to_csv(f"{path}/compiled_data.csv")
    print(dataf)

    sleep(1)
    print("JV Reverse Sweep")
    for (i, v) in enumerate(voltage_reverse):
        keithley.config_buffer(averages)
        keithley.source_voltage = v
        keithley.start_buffer()
        keithley.wait_for_buffer()
        current_reverse[i] = keithley.mean_current
        sleep(voltage_sweep_time)
    resistance_reverse = voltage_reverse/current_reverse
    current_reverse = current_reverse*1000/area
    power_reverse = voltage_reverse*current_reverse
    datar = determine_cell_parameters(voltage_reverse, current_reverse, power_reverse, solar_power, "Reverse")
    datar.to_csv(f"{path}/compiled_data.csv", mode = "a", header = False)
    print(datar)

data = pd.DataFrame({
    "Forward Voltage (V)": voltage,
    "Forward Current Density (mA/cm2)": current,
    "Forward Power Density (mW/cm2)": power,
    "Forward Efficiency (%)": power/solar_power * 100,
    "Forward Resistance (Ohms)": resistance,
    "Reverse Voltage (V)": voltage_reverse,
    "Reverse Current Density (mA/cm2)": current_reverse,
    "Reverse Power Density (mW/cm2)": power_reverse,
    "Reverse Efficiency (%)": power_reverse/solar_power * 100,
    "Reverse Resistance (Ohms)": resistance_reverse
})
data.to_csv(f"{path}/data.csv")


plt.plot(voltage, current, label = "Forward")
plt.plot(voltage_reverse, current_reverse, label = "Reverse")
plt.xlabel("Voltage (V)")
plt.ylabel("Current Density ($mA/cm^2$)")
plt.legend()
plt.show()
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

GPIB_connection = "GPIB::24"
data_points = 50
averages = 10
max_voltage = 1.2
min_voltage = 0

voltage = np.linspace(min_voltage, max_voltage, data_points)
current = np.zeros_like(voltage)
current_stds = np.zeros_like(voltage)
print(voltage)


with Keithley2400(GPIB_connection) as keithley:
    print(keithley.id)

    keithley.reset()
    keithley.use_front_terminals()
    keithley.apply_voltage()
    keithley.measure_current()

    keithley.enable_source()

    # JV sweep
    for (i, v) in enumerate(voltage):
        keithley.config_buffer(averages)
        keithley.source_voltage(v)
        keithley.start_buffer()
        keithley.wait_for_buffer()
        current[i] = keithley.means[0]
        sleep(1.0)
        current_stds[i] = keithley.standard_devs[0]

    data = pd.DataFrame({
        "Voltage (V)": voltage,
        "Current (A)": current,
        "Current Std (A)": current_stds
    })
    data.to_csv("./output/test.csv")
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
from time import sleep
from datetime import datetime
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QGridLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mppt.mppt import JV_SWEEP_STATE, MPP_STATE, DEAD_STATE, FORWARD_SCAN, REVERSE_SCAN, MpptData

GPIB = "GPIB::24"


class KeithleyMppt:
    def __init__(
            self,
            path: str,
            GPIB: str,
            cell_name: str,
    ) -> None:
        self.path = path
        self.cell = MpptData(cell_name)
        self.keithley = Keithley2400(GPIB)


    def set_voltage_on_keithley(self, voltage: float, keithley: Keithley2400) -> None:
        if not self.keithley.open():
            print("ERROR: Please open Keithley ")
            return
        
        keithley.config_buffer(self.averages)
        keithley.source_voltage = voltage
        sleep(self.step_time)
        keithley.start_buffer()
        keithley.wait_for_buffer()


    def set_mppt_testing_parameters(
            self,
            low_voltage: float,
            high_voltage: float,
            step_voltage: float,
            scan_speed: float,
            jv_sample_rate_modifier: float,
            mpp_duration: float,
            mpp_sample_interval: float,
            cell_area: float,
            solar_irradiance: float,
            averages: int
    ) -> None:
        self.cell_area = cell_area
        self.solar_irradiance = solar_irradiance
        self.mpp_duration = mpp_duration
        self.mpp_sample_interval = mpp_sample_interval
        self.step_time = step_voltage/scan_speed
        self.sample_interval = self.step_time*jv_sample_rate_modifier
        self.step_voltage = step_voltage/1000
        self.low_voltage = low_voltage
        self.high_voltage = high_voltage
        self.data_points = 140
        self.averages = averages


    def JV_scan(
            self,
            direction: str,
    ) -> None:
        if direction == FORWARD_SCAN:
            voltage = np.linspace(self.low_voltage, self.high_voltage, self.data_points)
        elif direction == REVERSE_SCAN:
            voltage = np.linspace(self.high_voltage, self.low_voltage, self.data_points)
        else:
            print(f"ERROR: Scan direction, '{direction}', is invalid")
            return

        with self.keithley as keithley:
            for (i, v) in enumerate(voltage):
                self.set_voltage_on_keithley(voltage, keithley)
                current = keithley.mean_current

                self.cell.voltage.append(v)
                self.cell.current.append(current)
                self.cell.timestamp.append(datetime.now())

        self.cell.store()


    def perform_JV_scans(self):
        self.JV_scan(FORWARD_SCAN)
        self.JV_scan(REVERSE_SCAN)
        self.cell.format_results(self.cell_area, self.solar_irradiance, self.path)


    # NOTE: Still need a way to record and possibly plot data
    def perturb_and_observe(self, starting_voltage: float):
        dV = self.step_voltage
        V0 = starting_voltage
        direction = 1

        with self.keithley as keithley:
            self.set_voltage_on_keithley(V0, keithley)
            J0 = keithley.mean_current*1000/self.cell_area  # mA/cm2
            P0 = -1*V0*J0  # mW/cm2

            while True:
                V = V0 + direction*dV
                self.set_voltage_on_keithley(V, keithley)
                J = keithley.mean_current*1000/self.cell_area  # mA/cm2
                P = -1*V*J
                if P > P0:
                    if V > V0:
                        direction = 1
                    else:
                        direction = -1
                    P0 = P
                    V0 = V
                else:
                    if V > V0:
                        direction = -1
                    else:
                        direction = 1
                    P0 = P
                    V0 = V 


    def perturb_and_observe_with_predictave_current(self, starting_voltage: float):
        pass


    def perturb_and_observe_metastable_psc(self, starting_voltage: float):
        dV = self.step_voltage
        V0 = starting_voltage


    def routine_A(self) -> bool:
        pass


    def routine_B(self)-> bool:
        pass


# TODO: Need to implement this class in the KeithleyMppt class
class KeithleyPlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Plot Updates")
        self.setGeometry(0, 0, 1200, 700)

        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Set main layout to be a vertical box
        main_layout = QVBoxLayout(central_widget)

        # Create 5 subplots
        self.figure = Figure(figsize = (5, 2.5))
        self.canvas = FigureCanvas(self.figure)

        # Create axes and plots
        self.axes = self.figure.add_subplot(111)

        # Create a layout for the plot
        layout = QVBoxLayout()
        layout.addWidget(self.canvas)

        # Add the layout to the main layout
        main_layout.addLayout(layout)

        # Initialize data for plotting
        self.x_data = np.linspace(0, 10, 100)
        self.y_data = np.zeros_like(self.x_data)

        # Create the intial plot
        self.axes.plot()
        self.axes.set_xlabel("Voltage (V)")
        self.axes.set_ylabel("Current Density ($mA/cm^{2}$)")
        self.axes.set_title(f"JV Data")


    def update_plot_data(self, data: MpptData) -> None:
        self.axes.clear()

        # Update MPPT plot
        # TODO: Still need to figure out how to update the data properly
        # self.axes.plot(data.forward_durations, data.forward_relative_efficiencies, color = 'b', label = f"Current Density")
        # self.axes.plot(data.reverse_durations, data.reverse_relative_efficiencies, color = 'r', ls = ":", label = f"PCE")
        
        self.axes.set_xlabel("Duration")
        self.axes.set_ylabel("Current Density ($mA/cm^{2}$)")
        self.axes.set_title("MPPT")
        self.axes.legend()

        self.canvas.draw()
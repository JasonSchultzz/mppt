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
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
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
        self.keithley.reset()
        self.keithley.use_front_terminals()
        self.window = KeithleyPlotter()
        self.window.show()


    def measure_current(
            self,
            voltage: float,
            keithley: Keithley2400,
            include_timestamp: bool = False
    ) -> float | tuple[float, float]:
        if self.keithley.isShutdown:
            raise Exception("ERROR: Keithley is in shutdown state")
        
        print(f"Voltage: {voltage} V")
        keithley.config_buffer(self.averages)
        keithley.source_voltage = voltage
        sleep(self.step_time)
        keithley.start_buffer()
        keithley.wait_for_buffer()
        

        if include_timestamp:
            return keithley.mean_current, datetime.now()
        else:
            return keithley.mean_current


    def set_mppt_testing_parameters(
            self,
            low_voltage: float,
            high_voltage: float,
            step_voltage: float,
            scan_speed: float,
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
        self.step_voltage = step_voltage/1000  # Convert to V
        self.low_voltage = low_voltage
        self.high_voltage = high_voltage
        self.data_points = int((high_voltage-low_voltage)/self.step_voltage)
        self.averages = averages


    def JV_scan(
            self,
            direction: str,
            keithley: Keithley2400
    ) -> None:
        if direction == FORWARD_SCAN:
            voltage = np.linspace(self.low_voltage, self.high_voltage, self.data_points)
        elif direction == REVERSE_SCAN:
            voltage = np.linspace(self.high_voltage, self.low_voltage, self.data_points)
        else:
            print(f"ERROR: Scan direction, '{direction}', is invalid")
            return

        for V in voltage:
            current, timestamp = self.measure_current(V, keithley, include_timestamp = True)

            self.cell.voltage.append(V)
            self.cell.current.append(current)
            self.cell.timestamp.append(timestamp)

        self.cell.store()


    def perform_JV_scans(self):
        with self.keithley as keithley:
            keithley.enable_source()
            self.JV_scan(FORWARD_SCAN, keithley)
            self.JV_scan(REVERSE_SCAN, keithley)
        self.window.update_JV_plot_data(self.cell, self.cell_area)
        self.cell.format_results(self.cell_area, self.solar_irradiance, self.path)


    def perturb_and_observe(self, starting_voltage: float) -> None:
        dV = self.step_voltage
        Vo = starting_voltage
        direction = 1

        with self.keithley as keithley:
            keithley.enable_source()
            io, to = self.measure_current(Vo, keithley, include_timestamp = True)
            Po = -Vo*io  # mW/cm2
            self.cell.append_data(Vo, io, to)

            while True:
                V = Vo + direction*dV
                i, t = self.measure_current(Vo, keithley, include_timestamp = True)
                P = -V*i
                if P > Po:
                    if V > Vo:
                        direction = 1
                    else:
                        direction = -1
                else:
                    if V > Vo:
                        direction = -1
                    else:
                        direction = 1

                self.cell.append_data(V, i, t)
                self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)
                Po = P
                Vo = V 


    def perturb_and_observe_with_predictave_current(self, starting_voltage: float):
        pass

    
    # From paper, DOI: https://doi.org/10.5796/electrochemistry.20-00022
    # "Development of a New MPPT Method for PCE Measurement of Metastable PSC"
    # x in the flow chart seems to be a tolerance value for dP/dt
    def perturb_and_observe_metastable_psc(
            self,
            starting_voltage: float,
            tolerance: float,
            delay_time: float
    ) -> None:
        dV = self.step_voltage
        Vo = starting_voltage

        with self.keithley as keithley:
            keithley.enable_source()
            io, to = self.measure_current(Vo, keithley, include_timestamp = True)
            Po = Vo*io
            self.cell.append_data(Vo, io, to)
            self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)

            # TODO: Where to store voltage and current values?
            while True:
                V = Vo + dV
                P, t = self.routine_A(V, Po, to, delay_time, tolerance, keithley)
                self.cell.append_data(Vo, io, to)
                self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)

                if P > Po:
                    if V <= Vo:
                        Vo = V
                        Po = P
                        # Routine B is just Routine A but with a voltage pertubation
                        V = V - 2*dV
                        P = self.routine_A(V, Po, to, delay_time, tolerance, keithley)
                        self.cell.append_data(Vo, io, to)
                        self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)

                else:
                    if V > Vo:
                        Vo = V
                        Po = P
                        # Routine B is just Routine A but with a voltage pertubation
                        V = V - 2*dV
                        P = self.routine_A(V, Po, to, delay_time, tolerance, keithley)
                        self.cell.append_data(Vo, io, to)
                        self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)

                Vo = V
                Po = P


    def routine_A(
            self,
            V: float,
            Po: float,
            to: float,
            delay_time: float,
            tolerance: float,
            keithley: Keithley2400
    ) -> tuple[float, float]:
        i, t = self.measure_current(V, keithley, include_timestamp = True)
        P = V*i
        
        # NOTE: measure_current() already uses a pre-set delay time, should this be removed?
        sleep(delay_time)

        dW = self.calculate_dP_over_dt(P, Po, t, to)
        while dW < tolerance:
            Po = P
            to = t

            i, t = self.measure_current(V, keithley, include_timestamp = True)
            P = V*i
            dW = self.calculate_dP_over_dt(P, Po, t, to)
            # NOTE: dW should be in percent to match tolerance, should it not just be a ratio of dPnew/dPold?

        return P, t


    def calculate_dP_over_dt(self, P: float, Po: float, t: float, to: float) -> float:
        dP = np.abs(P - Po)
        dt = np.abs((t - to).total_seconds())
        return dP/dt


# TODO: Plot doesn't display at start, but does update once JV scans are done.
#       It currently does NOT live update on P&O algorithms
class KeithleyPlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Plot Updates")
        self.setGeometry(0, 0, 1200, 700)

        # Create central widget
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)

        # Set main layout to be a vertical box
        layout = QVBoxLayout(main_widget)

        # Create 5 subplots
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        # Create axes and plots
        self.axes = self.figure.add_subplot(111)

        # Create a layout for the plot
        layout.addWidget(self.canvas)

        # Create the intial plot
        self.axes.plot()


    def update_mppt_plot_data(self, data: MpptData, cell_area: float, solar_irradiance: float) -> None:
        self.axes.clear()
        time = []
        for t in data.timestamp:
            time.append((t - data.timestamp[0]).total_seconds()/60)  # Converting to minutes

        voltage = np.array(data.voltage)
        current_density = np.array(data.current)*1000/cell_area  # mA/cm2
        efficiency = -voltage*current_density/solar_irradiance

        # Update MPPT plot
        self.axes.plot(time, voltage, color = 'b', label = f"Voltage (V)")
        self.axes.plot(time, efficiency, color = 'r', ls = ":", label = f"PCE")
        
        self.axes.set_xlabel("Duration (Min)")
        self.axes.set_title("MPPT")
        self.axes.legend()

        self.canvas.draw()


    def update_JV_plot_data(self, data: MpptData, cell_area: float) -> None:
        self.axes.clear()
        
        color_list = ['b', 'r']
        label_list = [FORWARD_SCAN, REVERSE_SCAN]
        for (i, sweep_data) in enumerate(data.sweep_data_list):
            voltage = sweep_data["Voltage (V)"]
            current_density = np.array(sweep_data["Current (A)"])*1000/cell_area  # mA/cm2

            # Update MPPT plot
            self.axes.plot(voltage, current_density, color = color_list[i], label = label_list[i])
        
        self.axes.set_xlabel("Voltage (V)")
        self.axes.set_ylabel("Current Density (%$mA/cm^{2}$)")
        self.axes.set_title("JV Scan")
        self.axes.legend()

        self.canvas.draw()
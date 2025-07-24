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
from mppt.mppt import FORWARD_SCAN, REVERSE_SCAN, MpptData


GPIB = "GPIB::24"
OUTPUT = "./output"


class KeithleyMppt:
    def __init__(
            self,
            GPIB: str,
            year: str,
            date: str,
            fabricator: str,
            cell_name: str,
            cell_area: float,
            solar_irradiance: float
    ) -> None:
        self.path = f"{OUTPUT}/{fabricator}/{year}/{date}"
        self.cell = MpptData(cell_name)
        self.cell_area = cell_area
        self.solar_irradiance = solar_irradiance

        self.keithley = Keithley2400(GPIB)
        self.keithley.reset()
        self.keithley.use_front_terminals()
        self.keithley.apply_voltage()
        self.keithley.measure_current()
        self.keithley.enable_source()

        self.window = KeithleyPlotter()
        self.window.show()


    def set_JV_parameters_with_time_step(
            self,
            high_voltage: float,
            low_voltage: float,
            step_voltage_mV: float,
            step_time_ms: float,
            averages: int
    ) -> None:
        self.step_time = step_time_ms/1000
        self.step_voltage = step_voltage_mV/1000  # Convert to V
        self.scan_speed = step_voltage_mV/(step_time_ms/1000)
        self.low_voltage = low_voltage
        self.high_voltage = high_voltage
        self.data_points = int((high_voltage-low_voltage)/self.step_voltage)
        self.averages = averages


    def set_JV_parameters_with_scan_speed(
            self,
            high_voltage: float,
            low_voltage: float,
            step_voltage_mV: float,
            scan_speed_mV_s: float,
            averages: int
    ) -> None:
        self.step_time = step_voltage_mV/scan_speed_mV_s
        self.step_voltage = step_voltage_mV/1000  # Convert to V
        self.scan_speed = scan_speed_mV_s
        self.low_voltage = low_voltage
        self.high_voltage = high_voltage
        self.data_points = int((high_voltage-low_voltage)/self.step_voltage)
        self.averages = averages


    def set_mppt_parameters(
            self,
            mpp_duration: float,
    ) -> None:
        self.mpp_duration = mpp_duration


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
            self.JV_scan(FORWARD_SCAN, keithley)
            self.JV_scan(REVERSE_SCAN, keithley)
        self.window.update_JV_plot_data(self.cell, self.cell_area)
        self.cell.format_results(self.cell_area, self.solar_irradiance, self.path, self.step_voltage*1000, self.step_time*1000, self.scan_speed)


    def perturb_and_observe(self, starting_voltage: float) -> None:
        dV = self.step_voltage
        Vo = starting_voltage
        direction = 1

        with self.keithley as keithley:
            io, to = self.measure_current(Vo, keithley, include_timestamp = True)
            Po = -1*Vo*io
            self.cell.append_data(Vo, io, to)

            mpp_start = datetime.now()
            while (datetime.now() - mpp_start).total_seconds() < self.mpp_duration:
                V = Vo + direction*dV
                i, t = self.measure_current(V, keithley, include_timestamp = True)
                P = -1*V*i
                
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
                Po = P
                Vo = V 

            self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)
            self.cell.format_mpp_results(self.cell_area, self.solar_irradiance, self.path)


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
            io, to = self.measure_current(Vo, keithley, include_timestamp = True)
            Po = Vo*io
            self.cell.append_data(Vo, io, to)
            

            mpp_start = datetime.now()
            while (datetime.now() - mpp_start).total_seconds() < self.mpp_duration:
                V = Vo + dV
                P, t = self.routine_A(V, Po, to, delay_time, tolerance, keithley)
                self.cell.append_data(Vo, io, to)

                if P > Po:
                    if V <= Vo:
                        Vo = V
                        Po = P
                        # Routine B is just Routine A but with a voltage pertubation
                        V = V - 2*dV
                        P = self.routine_A(V, Po, to, delay_time, tolerance, keithley)
                        self.cell.append_data(Vo, io, to)

                else:
                    if V > Vo:
                        Vo = V
                        Po = P
                        # Routine B is just Routine A but with a voltage pertubation
                        V = V - 2*dV
                        P = self.routine_A(V, Po, to, delay_time, tolerance, keithley)
                        self.cell.append_data(Vo, io, to)

                Vo = V
                Po = P

            self.window.update_mppt_plot_data(self.cell, self.cell_area, self.solar_irradiance)
            self.cell.format_mpp_results(self.cell_area, self.solar_irradiance, self.path)


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
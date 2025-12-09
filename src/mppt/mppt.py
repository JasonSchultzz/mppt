import numpy as np
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
import os
import toml


JV_STATE = "JV"
CONST_V_STATE = "Constant Voltage"
P_AND_O_STATE = "Simple P&O"
META_P_AND_O_STATE = "Metastable P&O"
DEAD_STATE = "Dead"
FORWARD_SCAN = "Forward"
REVERSE_SCAN = "Reverse"


class MpptData:
    def __init__(self, name: str) -> None:
        self.reset_data()
        self.sweep_data_list = []
        self.name = name
        self.state = JV_STATE

        self.initial_forward_voltage = None
        self.initial_forward_current_density = None
        self.initial_forward_time = None
        self.initial_forward_pce = None

        self.initial_reverse_voltage = None
        self.initial_reverse_current_density = None
        self.initial_reverse_time = None
        self.initial_reverse_pce = None

        self.recent_forward_voltage = None
        self.recent_forward_current_density = None
        self.recent_forward_pce = None

        self.recent_reverse_voltage = None
        self.recent_reverse_current_density = None
        self.recent_reverse_pce = None
        
        self.forward_relative_efficiencies = []
        self.reverse_relative_efficiencies = []
        self.forward_durations = []
        self.reverse_durations = []

        self.Vmpp = None
        self.first: bool = True


    def reset_data(self) -> None:
        self.voltage = []
        self.current = []
        self.timestamp = []


    def append_data(self, voltage: float, current: float, timestamp: datetime):
        self.voltage.append(voltage)
        self.current.append(current)
        self.timestamp.append(timestamp)
    

    def store(self) -> None:
        if self.voltage and self.current:  # Both are not empty
            self.sweep_data_list.append({
                "Timestamp": self.timestamp,
                "Voltage (V)": self.voltage,
                "Current (A)": self.current
                }
            )
            self.reset_data()


    def format_results(
            self,
            cell_area: float,
            solar_irradiance: float,
            directory: str,
            step_voltage_mV: float,
            step_time_ms: float,
            scan_speed_mV_s: float
    ) -> None:
        path = f"{directory}/{self.name}"
        if not os.path.exists(path):
            os.makedirs(path)

        # List should contain a forwards and reverse set of data
        if len(self.sweep_data_list) != 2:
            print(f"Time: {datetime.now()}, Channel {self.name}: Recording of forward or reverse JV sweep failed.")
            return
        
        forward_data = self.compile_sweep_data(self.sweep_data_list[0], cell_area, solar_irradiance, step_voltage_mV, step_time_ms, scan_speed_mV_s)
        reverse_data = self.compile_sweep_data(self.sweep_data_list[1], cell_area, solar_irradiance, step_voltage_mV, step_time_ms, scan_speed_mV_s)
        forward_data.to_csv(f"{path}/forward_scan.csv", mode = "a", header = not os.path.exists(f"{path}/forward_scan.csv"))
        reverse_data.to_csv(f"{path}/reverse_scan.csv", mode = "a", header = not os.path.exists(f"{path}/reverse_scan.csv"))

        compiled_data = {
                "Timestamp": [],
                "Duration (min)": [],
                "Direction": [],
                "Normalized PCE": [],
                "PCE (%)": [],
                "FF (%)": [],
                "Vmpp (V)": [],
                "Jmpp (mA/cm2)": [],
                "Voc (V)": [],
                "Jsc (mA/cm2)": [],
                "Rseries (Ohm)": [],
                "Rshunt (Ohm)": [],
                "Hysteresis Index": [],
                "Step Voltage (mV)": [],
                "Step Time (ms)": [],
                "Scan Rate (mV/s)": []
            }
        compiled_data = self.compile_data(compiled_data, forward_data, FORWARD_SCAN, cell_area, step_voltage_mV, step_time_ms, scan_speed_mV_s)
        compiled_data = self.compile_data(compiled_data, reverse_data, REVERSE_SCAN, cell_area, step_voltage_mV, step_time_ms, scan_speed_mV_s)

        # Determine Vmpp for MPPT as a simple average for now
        self.set_Vmpp_for_MPPT(self.Vmpp_forward, self.Vmpp_reverse)

        compiled_data = pd.DataFrame(compiled_data)
        compiled_data.to_csv(f"{path}/compiled_data.csv", mode = "a", header = not os.path.exists(f"{path}/compiled_data.csv"))

        # NOTE: Outputing data in a single xlsx spreadsheet causes issues when trying to append to
        # specific sheets

        # filename = f"{path}/data.xlsx"
        # try:
        #     with pd.ExcelWriter(filename, mode = "a") as writer:
        #         compiled_data.to_excel(writer, sheet_name = "Compiled JV Results")
        #         forward_data.to_excel(writer, sheet_name = "Forward Scan")
        #         reverse_data.to_excel(writer, sheet_name = "Reverse Scan")
        # except FileNotFoundError:
        #     with pd.ExcelWriter(filename, mode = "w") as writer:
        #         compiled_data.to_excel(writer, sheet_name = "Compiled JV Results")
        #         forward_data.to_excel(writer, sheet_name = "Forward Scan")
        #         reverse_data.to_excel(writer, sheet_name = "Reverse Scan")

        self.sweep_data_list = []
        if self.first:
            self.first = False


    def compile_sweep_data(
            self,
            data: pd.DataFrame,
            cell_area: float,
            solar_irradiance: float,
            step_voltage_mV: float,
            step_time_ms: float,
            scan_speed_mV_s: float
    ) -> pd.DataFrame:
        voltage = np.array(data["Voltage (V)"])  # V
        current_density = np.array(data["Current (A)"])*1000/cell_area  # mA/cm2
        power_density = voltage*current_density  # mW/cm2
        efficiency = -1*power_density*100/solar_irradiance
        return pd.DataFrame({
                "Timestamp": data["Timestamp"],
                "Voltage (V)": voltage,
                "Current Density (mA/cm2)": current_density,
                "Power Density (mW/cm2)": power_density,
                "PCE (%)": efficiency,
                "Step Voltage (mV)": np.ones(len(voltage))*step_voltage_mV,
                "Step Time (ms)": np.ones(len(voltage))*step_time_ms,
                "Scan Speed (mV/s)": np.ones(len(voltage))*scan_speed_mV_s
        })


    def compile_data(
            self,
            data: dict,
            sweep_data: pd.DataFrame,
            scan_direction: str,
            cell_area: float,
            step_volage_mV: float,
            step_time_ms: float,
            scan_speed_mV_s: float
    ) -> dict:
        
        mpp_index = np.argmin(sweep_data["Power Density (mW/cm2)"])
        voltage = sweep_data["Voltage (V)"]
        current_density = sweep_data["Current Density (mA/cm2)"]
        current = current_density*cell_area/1000  # convert back to Amps
        efficiency = sweep_data["PCE (%)"]
        Vmpp = voltage[mpp_index]

        # Attempt to calculate resistances. Will fail if the JV curve is such that the found
        # Vmpp is at the last point (ex if the curve ends up being a straight line)
        # If an error occurs, resistance values are not calculated
        try:
            Rseries = self.calculate_series_resistance(voltage, current)
        except Exception as e:
            print(f"ERROR: {e}\nExcluding resistances calculations")
            Rseries = np.nan
            Rshunt = np.nan
        finally:
            try:
                Rshunt = self.calculate_shunt_resistance(voltage, current, Rseries)
            except Exception as e:
                print(f"ERROR: {e}\nExcluding shunt resistances calculation")
                Rshunt = np.nan
        
        Jmpp = current_density[mpp_index]
        Jsc = np.interp(0, voltage, current_density)

        if scan_direction == FORWARD_SCAN:
            self.Vmpp_forward = Vmpp  # To determine average Vmpp
            hysteresis_index = None
            Voc = np.interp(0, current_density, voltage)

            if self.first:
                duration = 0
                relative_efficiency = 1

                # Storing intial results for JV plots and future calculations
                self.initial_forward_voltage = voltage
                self.initial_forward_current_density = current_density
                self.initial_forward_time = datetime.now()
                self.initial_forward_pce = efficiency[mpp_index]
            else:
                duration = (datetime.now() - self.initial_forward_time).seconds/60
                relative_efficiency = efficiency[mpp_index]/self.initial_forward_pce

                # Storing most recent JV results for plotting
                self.recent_forward_voltage = voltage
                self.recent_forward_current_density = current_density
                self.recent_forward_pce = efficiency[mpp_index]

            # Appending duration and normalized PCE to list for MPPT plotting
            self.forward_durations.append(duration)
            self.forward_relative_efficiencies.append(relative_efficiency)

        elif scan_direction == REVERSE_SCAN:
            Voc = np.interp(0, current_density[::-1], voltage[::-1])
            self.Vmpp_reverse = Vmpp

            if self.first:
                duration = 0
                relative_efficiency = 1

                # Storing intial results for JV plots and future calculations
                self.initial_reverse_voltage = voltage
                self.initial_reverse_current_density = current_density
                self.initial_reverse_time = datetime.now()
                self.initial_reverse_pce = efficiency[mpp_index]

                hysteresis_index = (self.initial_reverse_pce - self.initial_forward_pce)/self.initial_reverse_pce
            else:
                duration = (datetime.now() - self.initial_reverse_time).seconds/60
                relative_efficiency = efficiency[mpp_index]/self.initial_reverse_pce

                # Storing most recent JV results for plotting
                self.recent_reverse_voltage = voltage
                self.recent_reverse_current_density = current_density
                self.recent_reverse_pce = efficiency[mpp_index]

                hysteresis_index = (self.recent_reverse_pce - self.recent_forward_pce)/self.recent_reverse_pce

            # Appending duration and normalized PCE to list for MPPT plotting
            self.reverse_durations.append(duration)
            self.reverse_relative_efficiencies.append(relative_efficiency) 

        else:
            raise ValueError(f"{scan_direction} is an incorrect direction entry for compiling JV data.")
        
        FF = Vmpp*Jmpp*100/(Voc*Jsc)
        data["Timestamp"].append(datetime.now())
        data["Direction"].append(scan_direction)
        data["Duration (min)"].append(duration)
        data["Normalized PCE"].append(relative_efficiency)
        data["PCE (%)"].append(efficiency[mpp_index])
        data["FF (%)"].append(FF)
        data["Vmpp (V)"].append(Vmpp)
        data["Jmpp (mA/cm2)"] = Jmpp
        data["Voc (V)"].append(Voc)
        data["Jsc (mA/cm2)"].append(Jsc)
        data["Rseries (Ohm)"].append(Rseries)
        data["Rshunt (Ohm)"].append(Rshunt)
        data["Hysteresis Index"].append(hysteresis_index)
        data["Step Voltage (mV)"].append(step_volage_mV)
        data["Step Time (ms)"].append(step_time_ms)
        data["Scan Rate (mV/s)"].append(scan_speed_mV_s)
        return data


    def set_Vmpp_for_MPPT(self, Vmpp_forward: float, Vmpp_reverse: float) -> None:
        self.Vmpp = (Vmpp_forward + Vmpp_reverse)/2


    def calculate_series_resistance(self, voltage, current) -> float:
        # Calculate from V = Voc
        j_abs = np.abs(current)
        index = np.argmin(j_abs)
        x = voltage[index-10:index+10]
        y = current[index-10:index+10]
        m = self.determine_slope(x, y)
        return -1/m


    def calculate_shunt_resistance(self, voltage, current, Rseries) -> float:
        # Calculate from V = 0
        v_abs = np.abs(voltage)
        index = np.argmin(v_abs)
        x = voltage[index-10:index+10]
        y = current[index-10:index+10]
        m = self.determine_slope(x, y)
        return (-1/m - Rseries)


    def determine_slope(self, x, y) -> float:
        m, b = np.polyfit(x, y, 1)
        return m
    

    def format_mpp_results(
            self,
            cell_area: float,
            solar_irradiance: float,
            directory: str,
            mpp_state: str
    ) -> None:
        # Check to see that the voltage and current lists have data in it
        if not self.voltage or not self.current:
            return
        
        voltage = np.array(self.voltage)
        current_density = np.array(self.current)*1000/cell_area  # mA/cm2
        power_density = -1*voltage*current_density
        efficiency = power_density*100/solar_irradiance
        state = np.full(len(voltage), mpp_state)
        path = f"{directory}/{self.name}"

        compiled_data = pd.DataFrame({
            "Timestamp": self.timestamp,
            "Voltage (V)": self.voltage,
            "Current Density (mA/cm2)": current_density,
            "Power Density (mW/cm2)": power_density,
            "PCE (%)": efficiency,
            "MPP Format": state
        })
        compiled_data.to_csv(f"{path}/mppt_data.csv", mode = "a", header = not os.path.exists(f"{path}/mppt_data.csv"))

        # filename = f"{path}/data.xlsx"
        # try:
        #     with pd.ExcelWriter(filename, mode = "a",) as writer:
        #         compiled_data.to_excel(writer, sheet_name = "MPPT")
        # except FileNotFoundError:
        #     with pd.ExcelWriter(filename, mode = "w") as writer:
        #         compiled_data.to_excel(writer, sheet_name = "MPPT")

        self.reset_data()


@dataclass
class InputData:
    device_name: str
    device_port: str

    fabricator: str
    year: str
    date: str
    cell_names: list[str]
    cell_area: float | int
    irradiance: float | int

    high_voltage: float | int
    low_voltage: float | int
    jv_step_voltage_mV: float | int
    jv_step_time_ms: int
    jv_sample_rate_modifier: int
    mppt_method: str
    periodic_jv_scans: bool

    mppt_duration: int
    mppt_step_voltage_mV: float | int
    mppt_step_time_ms: int
    mppt_sample_interval_ms: int
    mppt_tolerance: float | int

    buffer_length: int
    buffer_time: int


    def __init__(self, file: str) -> None:
        with open(file, "r") as f:
            config = toml.load(f)

        self.device_name = config["device"]["name"]
        self.device_port = config["device"]["port"]

        self.fabricator = config["cell"]["fabricator"]
        self.year = config["cell"]["year"]
        self.date = config["cell"]["date"]
        self.cell_names = config["cell"]["names"]
        self.cell_area = config["cell"]["aperture_area"]
        self.irradiance = config["cell"]["solar_irradiance"]

        self.high_voltage = config["experiment"]["high_voltage"]
        self.low_voltage = config["experiment"]["low_voltage"]
        self.jv_step_voltage_mV = config["experiment"]["jv_step_voltage_mV"]
        self.jv_step_time_ms = config["experiment"]["jv_step_time_ms"]
        self.jv_sample_rate_modifier = config["experiment"]["jv_sample_rate_modifier"]
        self.mppt_method = config["experiment"]["mppt_method"]
        self.periodic_jv_scans = config["experiment"]["periodic_jv_scans"]

        self.mppt_duration = config["mppt"]["duration"]
        self.mppt_step_voltage_mV = config["mppt"]["step_voltage_mV"]
        self.mppt_step_time_ms = config["mppt"]["step_time_ms"]
        self.mppt_sample_interval_ms = config["mppt"]["sample_interval"]
        self.mppt_tolerance = config["mppt"]["tolerance"]

        self.buffer_length = config["buffer"]["max_length"]
        self.buffer_time = config["buffer"]["max_time"]

        self.validate()


    def validate(self):
        if not isinstance(self.device_name, str):
            raise ValueError(f"Device Name '{self.device_name}' must be a string.")
        if not isinstance(self.device_port, str):
            raise ValueError(f"Device Port '{self.device_port}' must be a string.")
        
        if not isinstance(self.fabricator, str):
            raise ValueError(f"Fabricator '{self.fabricator}' must be a string.")
        if not isinstance(self.year, str):
            raise ValueError("Year must be a string.")
        if not isinstance(self.date, str):
            raise ValueError("Date must be a string.")
        if not isinstance(self.cell_names, list):
            raise ValueError("Cell Names must be a string.")
        for name in self.cell_names:
            if not isinstance(name, str):
                raise ValueError(f"Cell name '{name}' must be a string.")
        if not isinstance(self.cell_area, (float, int)):
            raise ValueError(f"Cell area '{self.cell_area}' must be a float or integer.")
        if not isinstance(self.irradiance, (float, int)):
            raise ValueError(f"Irradiance '{self.irradiance}' must be a float or integer.")
        
        if not isinstance(self.high_voltage, (float, int)):
            raise ValueError(f"High voltage '{self.high_voltage}' must be a float or integer.")
        if not isinstance(self.low_voltage, (float, int)):
            raise ValueError(f"Low voltage '{self.low_voltage}' must be a float or integer.")

        if not isinstance(self.jv_step_voltage_mV, (float, int)):
            raise ValueError(f"JV step voltage '{self.jv_step_voltage_mV}' must be a float or integer.")
        if not isinstance(self.jv_step_time_ms, int):
            raise ValueError(f"JV step time '{self.jv_step_time_ms}' must be a integer.")
        if not isinstance(self.jv_sample_rate_modifier, int):
            raise ValueError(f"JV sample rate modifier '{self.jv_sample_rate_modifier}' must be a integer.")
        if (self.mppt_method != CONST_V_STATE) and (self.mppt_method != P_AND_O_STATE) and (self.mppt_method != META_P_AND_O_STATE):
            raise ValueError(f"Invalid MPPT method '{self.mppt_method}'. Viable options are:\n  {CONST_V_STATE}\n  {P_AND_O_STATE}\n  {META_P_AND_O_STATE}")
        if not isinstance(self.periodic_jv_scans, bool):
            raise ValueError(f"Periodic JV scans '{self.periodic_jv_scans}' must be a boolean.")

        if not isinstance(self.mppt_duration, int):
            raise ValueError(f"MPPT duration '{self.mppt_duration}' must be a integer.")
        if not isinstance(self.mppt_step_voltage_mV, (float, int)):
            raise ValueError(f"MPPT step voltage '{self.mppt_step_voltage_mV}' must be a float or integer.")
        if not isinstance(self.mppt_step_time_ms, int):
            raise ValueError(f"MPPT step time '{self.mppt_step_time_ms}' must be a integer.")
        if not isinstance(self.mppt_sample_interval_ms, int):
            raise ValueError(f"MPPT sample interval'{self.mppt_sample_interval_ms}' must be an integer.")
        if not isinstance(self.mppt_tolerance, (float, int)):
            raise ValueError(f"MPPT tolerance '{self.mppt_tolerance}' must be a float or integer.")
        
        if not isinstance(self.buffer_length, int):
            raise ValueError(f"Max Buffer length '{self.buffer_length}' must be an integer.")
        if not isinstance(self.buffer_time, int):
            raise ValueError(f"Max Buffer time '{self.buffer_time}' must be an integer.")
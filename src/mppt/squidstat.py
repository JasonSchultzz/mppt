import numpy as np
from datetime import datetime
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QGridLayout, QMessageBox
from PySide6.QtCore import QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from SquidstatPyLibrary import AisDeviceTracker, AisExperiment, AisSteppedVoltageElement, AisConstantPotElement, AisErrorCode
from mppt.mppt import JV_STATE, CONST_V_STATE, P_AND_O_STATE, META_P_AND_O_STATE, DEAD_STATE, MpptData, InputData


OUTPUT = "./output"


class SquidstatMppt:
    def __init__(
            self,
            config: InputData
    ) -> None:
        if not isinstance(config, InputData):
            raise ValueError("Input data was not inputted correctly as the 'InputData' object.")

        assert(len(config.cell_names) <= 4)
        self.channel_data: list[MpptData] = []
        for channel_name in config.cell_names:
            self.channel_data.append(MpptData(channel_name))

        self.window = SquidPlotter()
        self.window.show()

        self.cell_area = config.cell_area
        self.solar_irradiance = config.irradiance
        self.main_state = config.mppt_method

        self.path = f"{OUTPUT}/{config.fabricator}/{config.year}/{config.date}"
        self.tracker = AisDeviceTracker.Instance()
        self.tracker.newDeviceConnected.connect(lambda deviceName: print("Device is Connected: %s" % deviceName))
        self.tracker.connectToDeviceOnComPort(config.device_port)
        self.handler = self.tracker.getInstrumentHandler(config.device_name)
        self.connect()

        self.periodic_jv_scans = config.periodic_jv_scans
        self.max_buffer_length = config.buffer_length
        self.max_buffer_time = config.buffer_time

        self.set_JV_parameters(
            high_voltage = config.high_voltage,
            low_voltage = config.low_voltage,
            step_voltage_mV = config.jv_step_voltage_mV,
            step_time_ms = config.jv_step_time_ms,
            jv_sample_rate_modifier = config.jv_sample_rate_modifier
        )
        self.set_mppt_parameters(
            duration_seconds = config.mppt_duration,
            step_voltage_mV = config.mppt_step_voltage_mV,
            step_time_ms = config.mppt_step_time_ms,
            sample_interval_ms = config.mppt_sample_interval_ms,
            tolerance = config.mppt_tolerance
        )


    def connect(self) -> None:
        # What occurs when a new expierment is started
        self.handler.experimentNewElementStarting.connect(lambda channel, data: self.experiment_started(channel))
        
        # What happens when data is recorded
        self.handler.activeDCDataReady.connect(lambda channel, data: self.data_received(channel, data))

        # What happens when an experiment is finished
        self.handler.experimentStopped.connect(lambda channel: self.experiment_finished(channel))

        # What happens when an error occurs
        self.handler.deviceError.connect(lambda channel, error: print(f"Device Error: {error}"))

    
    def set_JV_parameters(
            self,
            high_voltage: float,
            low_voltage: float,
            step_voltage_mV: float,
            step_time_ms: float,
            jv_sample_rate_modifier: int = 1
    ) -> None:
        self.step_time = step_time_ms/1000
        sample_interval = self.step_time*jv_sample_rate_modifier
        self.step_voltage = step_voltage_mV/1000
        self.scan_speed = step_voltage_mV/(step_time_ms/1000)

        self.experiment = AisExperiment()
        self.forwardJVSweep = AisSteppedVoltageElement(
            low_voltage,
            high_voltage,
            self.step_voltage,
            self.step_time,
            sample_interval
        )
        self.reverseJVSweep = AisSteppedVoltageElement(
            high_voltage,
            low_voltage,
            self.step_voltage,
            self.step_time,
            sample_interval
        )
        
        self.experiment.appendElement(self.forwardJVSweep)
        self.experiment.appendElement(self.reverseJVSweep)
        

    def set_mppt_parameters(
            self,
            duration_seconds: int,
            step_voltage_mV: int,
            step_time_ms: int,
            sample_interval_ms: int,
            tolerance: float = 1.0
    ) -> None:
        self.mppt_duration = duration_seconds
        self.mppt_step_voltage = step_voltage_mV/1000
        self.mppt_step_time = step_time_ms/1000
        self.mppt_sample_interval = sample_interval_ms/1000
        self.Vo = None
        self.Po = None
        self.mppt_direction = 1
        self.tolerance = tolerance


    def start_JV_scans(self) -> None:
        # Ensure list is not empty -> at least one channel is used
        assert(self.channel_data)
        for (i, _) in enumerate(self.channel_data):
            self.handler.uploadExperimentToChannel(i, self.experiment)
            self.handler.startUploadedExperiment(i)


    def start_const_voltage(self) -> None:
        assert(self.channel_data)
        for (i, channel) in enumerate(self.channel_data):
            constant_potential = AisConstantPotElement(
                channel.Vmpp,
                self.mppt_sample_interval,
                self.mppt_duration
            )
            constant_potential_experiment = AisExperiment()
            constant_potential_experiment.appendElement(constant_potential)
            self.handler.uploadExperimentToChannel(i, constant_potential_experiment)
            self.handler.startUploadedExperiment(i)


    def set_manual_mppt_voltage(self, channel: int, voltage: float) -> None:
        error = self.handler.setManualModeConstantVoltage(channel, voltage)
        if error.value() != AisErrorCode.Success:
            print(f"Time: {datetime.now()}, Channel {channel}: {error.message()}")


    def stop_mppt_experiment(self, channel: int, timer: QTimer) -> None:
            timer.stop()
            error = self.handler.stopExperiment(channel)
            if error.value() != AisErrorCode.Success:
                print(f"Time: {datetime.now()}, Channel {channel}: {error.message()}")


    def set_timer(self, channel: int, delay_ms: float) -> QTimer:
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.stop_mppt_experiment(channel, timer))
        timer.start(delay_ms)
        return timer


    def start_mppt_experiment(self) -> None:
        assert(self.channel_data)
        timer: list[QTimer] = []
        for (i, channel) in enumerate(self.channel_data):
            # Starting experiment
            error = self.handler.startManualExperiment(i)
            if error.value() != AisErrorCode.Success:
                print(f"Time: {datetime.now()}, Channel {i}: {error.message()}")

            # Setting sample interval for manual mppt experiment
            error = self.handler.setManualModeSamplingInterval(i, self.mppt_step_time)
            if error.value() != AisErrorCode.Success:
                print(f"Time: {datetime.now()}, Channel {i}: {error.message()}")

            error = self.handler.setManualModeConstantVoltage(i, channel.Vmpp)
            if error.value() != AisErrorCode.Success:
                print(f"Time: {datetime.now()}, Channel {i}: {error.message()}")

            if self.periodic_jv_scans:
                print(f"Time: {datetime.now()}, Channel {i}: MPPT started at {self.channel_data[i].Vmpp:.2f} V for {self.mppt_duration} seconds.")
            else:
                print(f"Time: {datetime.now()}, Channel {i}: MPPT started at {self.channel_data[i].Vmpp:.2f} V until stopped.")

            # Set timer to stop the MPPT experiment if duration is set to end.
            if self.periodic_jv_scans:
                if len(self.channel_data) > 1:
                    # NOTE: singleShot doesn't seem to work when multiple channels are used
                    timer.append(self.set_timer(i, self.mppt_duration*1000))
                else:
                    # NOTE: Appending only 1 QTimer to the list above does not seem to work?
                    QTimer.singleShot(self.mppt_duration*1000, lambda:self.stop_mppt_experiment(i))


    def preturb_and_observe(self, channel: int, voltage: float, current: float, timestamp: float)-> None:
        if self.Vo == None:
            # Sets the initial values for P&O
            self.Vo = voltage
            self.Po = -1*voltage*current
            V = voltage + self.mppt_direction * self.mppt_step_voltage
            self.set_manual_mppt_voltage(channel, V)
        else:
            P = -1*voltage*current

            if P > self.Po:
                if voltage > self.Vo:
                    self.mppt_direction = 1
                else:
                    self.mppt_direction = -1
            else:
                if voltage > self.Vo:
                    self.mppt_direction = -1
                else:
                    self.mppt_direction = 1

            self.Vo = voltage
            self.Po = P
            V = voltage + self.mppt_direction * self.mppt_step_voltage
            self.set_manual_mppt_voltage(channel, V)

        self.channel_data[channel].append_data(voltage, current, timestamp)
        
        # No periodic JV scans
        if not self.periodic_jv_scans:
            if len(self.channel_data[channel].voltage) > self.max_buffer_length:
                self.channel_data[channel].format_mpp_results(
                    self.cell_area,
                    self.solar_irradiance,
                    self.path,
                    self.main_state
                )


    # From paper, DOI: https://doi.org/10.5796/electrochemistry.20-00022
    # "Development of a New MPPT Method for PCE Measurement of Metastable PSC"
    # x in the flow chart seems to be a tolerance value for dP/dt
    def p_and_o_metastable_psc(
            self,
            channel: int,
            voltage: float,
            current: float,
            timestamp: float,
            tolerance: float
    )-> None:
        if self.Vo == None:
            # Sets the initial values for P&O
            self.Vo = voltage
            self.Po = -1*voltage*current
            V = voltage + self.mppt_step_voltage
            self.set_manual_mppt_voltage(channel, V)
            self.call_routine_A = True
        elif self.call_routine_A:
            P = -1*voltage*current
            if np.abs((P/self.Po)*100 - 100) < tolerance:
                self.call_routine_A = False
                V = voltage + self.mppt_step_voltage
                self.set_manual_mppt_voltage(channel, V)
            self.Po = P
            self.Vo = voltage
        else:
            P = -1*voltage*current

            if P > self.Po:
                if voltage <= self.Vo:
                    self.Vo = voltage
                    self.Po = P
                    V = voltage - 2*self.mppt_step_voltage
                    self.set_manual_mppt_voltage(channel, V)
                    self.call_routine_A = True
                else:
                    self.Vo = voltage
                    self.Po = P
                    V = voltage + self.mppt_step_voltage
                    self.set_manual_mppt_voltage(channel, V)
            else:
                if voltage > self.Vo:
                    self.Vo = voltage
                    self.Po = P
                    V = voltage - 2*self.mppt_step_voltage
                    self.set_manual_mppt_voltage(channel, V)
                    self.call_routine_A = True
                else:
                    self.Vo = voltage
                    self.Po = P
                    V = voltage + self.mppt_step_voltage
                    self.set_manual_mppt_voltage(channel, V)

        self.channel_data[channel].append_data(voltage, current, timestamp)

        # No periodic JV scans
        if not self.periodic_jv_scans:
            if len(self.channel_data[channel].voltage) > self.max_buffer_length:
                self.channel_data[channel].format_mpp_results(
                    self.cell_area,
                    self.solar_irradiance,
                    self.path,
                    self.main_state
                )


    # Function is called when a new experiment element starts
    def experiment_started(self, channel: int) -> None:
        if self.channel_data[channel].state == JV_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: JV scan started")
            self.channel_data[channel].store()
        elif self.channel_data[channel].state == CONST_V_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: Constant voltage started at {self.channel_data[channel].Vmpp:.2f} for {self.const_voltage_duration} seconds.")
        elif self.channel_data[channel].state == P_AND_O_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: MPPT started at {self.channel_data[channel].Vmpp:.2f}")
        elif self.channel_data[channel].state == META_P_AND_O_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: MPPT started at {self.channel_data[channel].Vmpp:.2f}")
        else:  # Dead state
            print(f"Time: {datetime.now()}, Channel {channel}: DEAD STATE - SHOULD NOT BE STARTING AN EXPERIMENT")


    # Function is called everytime data is collected from Squidstat
    def data_received(self, channel: int, data) -> None:
        if self.channel_data[channel].state == P_AND_O_STATE:
            self.preturb_and_observe(
                channel,
                data.workingElectrodeVoltage,
                data.current,
                datetime.now()
            )
        elif self.channel_data[channel].state == META_P_AND_O_STATE:
            self.p_and_o_metastable_psc(
                channel,
                data.workingElectrodeVoltage,
                data.current,
                datetime.now(),
                self.tolerance
            )
        else:
            self.channel_data[channel].append_data(
                data.workingElectrodeVoltage,
                data.current,
                datetime.now()
            )


    # Function is called when a channel finishes an experiment
    def experiment_finished(self, channel: int) -> None:
        # JV Sweeps finished. Compile data and proceed to held MPP state if all other channels are also finished.
        if self.channel_data[channel].state == JV_STATE:
            self.channel_data[channel].state = self.main_state
            self.channel_data[channel].store()
            self.channel_data[channel].format_results(
                self.cell_area,
                self.solar_irradiance,
                self.path,
                self.step_voltage*1000,
                self.step_time*1000,
                self.scan_speed
            )
            print(f"Time: {datetime.now()}, Channel {channel}: JV scan complete")
            if self.confirm_all_matching_states(self.main_state):
                print(f"Time: {datetime.now()}, All JV scans complete")
                self.window.update_jv_plot(self.channel_data)
                self.window.update_mppt_plot(self.channel_data)
                if self.main_state == CONST_V_STATE:
                    self.start_const_voltage()
                elif (self.main_state == P_AND_O_STATE) or (self.main_state == META_P_AND_O_STATE):
                    self.start_mppt_experiment()

        # MPP duration elasped. Proceed to JV sweeps if all other channels are also finished.
        elif self.channel_data[channel].state == self.main_state:
            self.channel_data[channel].format_mpp_results(
                self.cell_area,
                self.solar_irradiance,
                self.path,
                self.main_state
            )
            print(f"Time: {datetime.now()}, Channel {channel}: MPPT duration elapsed")
            self.channel_data[channel].state = JV_STATE
            if self.confirm_all_matching_states(JV_STATE):
                print(f"Time: {datetime.now()}, All MPP durations elapsed. Starting JV scans")
                self.start_JV_scans()

        # Dead state
        else:  
            # Need to check that every other channel has reached dead state to quit
            # app.quit()
            pass


    def confirm_all_matching_states(self, state: int) -> bool:
        print("Channel States: ")
        for channel in self.channel_data:
            print(f"  {channel.name}: {channel.state}")
            if channel.state != state:
                return False
        return True
        

    def __del__(self):
        # For manual experiments, this will stop the experiment running on the Squidstat
        # if this object no longer exists (when the window is closed or program killed)
        for (i, channel) in enumerate(self.channel_data):
            error = self.handler.stopExperiment(i)
            if error.value() != AisErrorCode.Success:
                print(f"Time: {datetime.now()}, Channel {i}: {error.message()}")


class SquidPlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Plot Updates")
        self.setGeometry(0, 0, 1200, 700)

        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Set main layout to be a vertical box
        main_layout = QVBoxLayout(central_widget)

        # Create a grid layout for first 4 plots
        grid_layout = QGridLayout()

        # Create 5 subplots
        self.figures = [Figure(figsize = (5, 2.5)) for _ in range(5)]
        self.canvas = [FigureCanvas(fig) for fig in self.figures]

        # Create axes and plots
        self.axes = [fig.add_subplot(111) for fig in self.figures]

        # Create the grid for the first 4 plots
        for i, canvas_item in enumerate(self.canvas[:4]):
            row = i // 2  # 2 rows
            col = i % 2  # 2 columns
            grid_layout.addWidget(canvas_item, row, col)

        # Add the grid layout to the main layout
        main_layout.addLayout(grid_layout)

        # Create a separate layout for the 5th plot
        bottom_layout = QVBoxLayout()
        bottom_layout.addWidget(self.canvas[4])

        # Add the bottom plot layout to the main layout
        main_layout.addLayout(bottom_layout)

        # Initialize data for plotting
        self.x_data = np.linspace(0, 10, 100)
        self.y_data = [np.zeros_like(self.x_data) for _ in range(5)]

        # Create the intial plots
        for i, ax in enumerate(self.axes):
            ax.plot()
            if i == 4:
                ax.set_xlabel("Duration")
                ax.set_ylabel("Normalized PCE")
                ax.set_title("MPPT")
                
            else:
                ax.set_xlabel("Voltage (V)")
                ax.set_ylabel("Current Density ($mA/cm^{2}$)")
                ax.set_title(f"Channel {i+1} JV Data")


    # Slot function to handle close event
    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Exit Confirmation', 'Are you sure you want to exit?', 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                    QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


    def update_jv_plot(self, channel_data: list[MpptData]) -> None:
        # Update each plot
        self.axes[4].clear()
        for i, data in enumerate(channel_data):
            ax = self.axes[i]
            ax.clear()  # Clear the old plot
            forward_voltage = data.initial_forward_voltage
            reverse_voltage = data.initial_reverse_voltage
            forward_current_density = data.initial_forward_current_density
            reverse_current_density = data.initial_reverse_current_density

            # Plot the initial JV sweep
            ax.plot(forward_voltage, forward_current_density, color = 'b', label = "Initial Forward")
            ax.plot(reverse_voltage, reverse_current_density, color = 'r', label = "Initial Reverse")

            forward_voltage = data.recent_forward_voltage
            reverse_voltage = data.recent_reverse_voltage
            forward_current_density = data.recent_forward_current_density
            reverse_current_density = data.recent_reverse_current_density
            if forward_voltage is not None and reverse_voltage is not None and forward_current_density is not None and reverse_current_density is not None:
                # Plot the latest JV sweep
                ax.plot(forward_voltage, forward_current_density, ls = ":", color = 'b', label = "Recent Forward")
                ax.plot(reverse_voltage, reverse_current_density, ls = ":", color = 'r', label = "Recent Reverse")

            # Set plots lables
            ax.set_xlabel("Voltage (V)")
            ax.set_ylabel("Current Density ($mA/cm^{2}$)")
            ax.set_title(f"Channel {i+1} JV Data")
            # ax.set_ylim((None, 0))  # View of Quadrant 4
            ax.legend()

        # Refresh the canvas to reflect the changes
        for canvas_item in self.canvas:
            canvas_item.draw()

    
    def update_mppt_plot(self, channel_data: list[MpptData]) -> None:
        # Update each plot
        self.axes[4].clear()
        mppt_channel_colors = ["r", "b", "g", "m"]
        for i, data in enumerate(channel_data):
            # Update MPPT plot
            self.axes[4].plot(data.forward_durations, data.forward_relative_efficiencies, color = mppt_channel_colors[i], label = f"Forward {i+1}")
            self.axes[4].plot(data.reverse_durations, data.reverse_relative_efficiencies, color = mppt_channel_colors[i], ls = ":", label = f"Reverse {i+1}")
            
            self.axes[4].set_xlabel("Duration")
            self.axes[4].set_ylabel("Normalized PCE")
            self.axes[4].set_title("MPPT")
            self.axes[4].legend()

            # Refresh the canvas to reflect the changes
            for canvas_item in self.canvas:
                canvas_item.draw()
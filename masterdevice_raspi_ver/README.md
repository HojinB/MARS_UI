
Master Device Control UI (Raspberry Pi Ver.)
📝 Overview
This document provides instructions for the web-based user interface designed for the precise control and monitoring of a dual-arm master device powered by a Raspberry Pi and a U2D2.

All communication between this UI, the master device, and the slave robot is built on gRPC, ensuring fast and stable data exchange.

📖 How to Use
Step 1: Connect to the Device
When you first launch the application, the connection page will appear.

Master Device gRPC Target: Enter the IP address and Port for the master device (Raspberry Pi).

Default: 192.168.0.43:50051

Slave Robot gRPC Target: Enter the IP address and Port for the slave robot that will receive the control data.

Default: 192.168.0.41:50054

Connect: Click the '⚡ Connect' button. Upon a successful gRPC connection, you will be automatically redirected to the main control UI.

Step 2: Main Control Interface
This screen is where you operate all functions of the master device.

Data Streaming:

Click 'Start Streaming' to begin sending data to the slave robot. The status indicator will turn green ('Active').

Click 'Stop Streaming' to halt the data stream.

Real-time Operation:

Arm Status: The status panels for each arm show whether it is in 'Position Control' (green) or 'Gravity Compensation' (red) mode.

Torque Mode: Adjust the intensity of the gravity compensation. You can set a precise value between 0.0 and 1.0 using the input field or slider.

Go Home: Click the 'Go Home' button to move the robot to its predefined home position.

Data Recording:

Recording: Click this button to start logging encoder data. The button will change to 'Stop'; click it again to pause.

Clear: Deletes all currently recorded data from memory.

Save As: Saves the recorded data to a new .csv file in the project's log directory.

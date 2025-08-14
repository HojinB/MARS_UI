import grpc
import GRPC.stubs.masterdevice_pb2 as masterdevice_pb2
import GRPC.stubs.masterdevice_pb2_grpc as masterdevice_pb2_grpc

# RAS_IP = '192.168.0.43'
# SLAVE_IP = ''
# PORT = 8081

def send_connect_command(ip, port, command):
    with grpc.insecure_channel(f"{ip}:{port}") as channel:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.ConnectCommand(command=command)
        response = stub.Connect(request)
        print(f"[UI] Master Connect response: {response.message}")
        return response.message.strip().lower()

def send_homing_command(ip, port, command):
    with grpc.insecure_channel(f"{ip}:{port}") as channel:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.HomingCommand(command=command)
        response = stub.Homing(request)
        print(f"[UI] Master Homing response: {response.message}")
        return response.message.strip()  # 응답값 반환 추가

def send_master_teleop_command(ip, port, command):
    with grpc.insecure_channel(f"{ip}:{port}") as channel:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.TeleoperationCommand1(command=command)
        response = stub.Teleoperation1(request)
        print(f"[UI] Master Teleop response: {response.message}")
        return response.message.strip()  # 응답값 반환 추가
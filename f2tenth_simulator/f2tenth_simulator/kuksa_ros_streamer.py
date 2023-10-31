#!/usr/bin/env python3
from collections.abc import Callable, Iterable, Mapping
from typing import Any
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from kuksa_client.grpc import VSSClient
import time
import threading

value_torque = 0.
value_steering_angle = 0.
value_teleop_enabled = False


class KuksaROS2Streamer(Node):
    def __init__(self):
        print("Starting Kuksa ROS2 Streamer ...")
        super().__init__("kuksa_ros2_streamer")
        self.publisher = self.create_publisher(Twist, "/turtle1/cmd_vel", 10)

    def publish(self):
        global value_torque, value_steering_angle, value_teleop_enabled

        if value_teleop_enabled:
            if value_torque > 0:
                msg = Twist()
                msg.linear.x = value_torque
                msg.angular.z = value_steering_angle

                print("Publishing " + str(msg))
                self.publisher.publish(msg)


class KuksaDataSubscriber(threading.Thread):

    def __init__(self, pub):
        super(KuksaDataSubscriber, self).__init__()
        self.pub = pub


    def run(self) -> None:
        global value_torque, value_steering_angle, value_teleop_enabled
        print("Starting Kuksa Data Subscriber Thread ...")
        with VSSClient("data_broker", 55555) as client:
            for updates in client.subscribe_target_values(
                [
                    "Vehicle.Teleoperation.Torque",
                    "Vehicle.Teleoperation.SteeringAngle",
                    "Vehicle.Teleoperation.IsEnabled",
                ]
            ):
                if updates.get("Vehicle.Teleoperation.Torque") is not None:
                    value_torque = updates.get("Vehicle.Teleoperation.Torque").value
                if updates.get("Vehicle.Teleoperation.SteeringAngle") is not None:
                    value_steering_angle = updates.get(
                        "Vehicle.Teleoperation.SteeringAngle"
                    ).value
                if updates.get("Vehicle.Teleoperation.IsEnabled") is not None:
                    value_teleop_enabled = updates.get(
                        "Vehicle.Teleoperation.IsEnabled"
                    ).value
                self.pub.publish()


def main():

    # Create ROS2 Node
    rclpy.init()
    ros2Pub = KuksaROS2Streamer()

    # Subsribe to Kuksa
    kuksaThread = KuksaDataSubscriber(ros2Pub)

    # Start thread and ros2 node
    kuksaThread.start()
    rclpy.spin(ros2Pub)

    # Destroy nodes on exit
    ros2Pub.destroy_node()
    rclpy.shutdown()

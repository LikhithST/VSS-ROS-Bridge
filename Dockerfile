FROM osrf/ros:humble-desktop-full

# Set environment 
ENV width 2920
ENV height 2180
ENV x_coord 1
ENV y_coord 1
ENV angle 0

WORKDIR /src
COPY . .
RUN . /opt/ros/humble/setup.sh
RUN apt update && apt install -y python3-pip 
RUN pip3 install kuksa_client
RUN pip install setuptools==58.2.0
RUN colcon build
CMD . ./install/setup.sh; . /opt/ros/humble/setup.sh; ros2 run turtlesim turtlesim_node& ros2 run f2tenth_simulator talker
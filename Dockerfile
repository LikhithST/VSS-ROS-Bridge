# Builder stage
FROM ros:humble-ros-core-jammy as builder

RUN apt update && apt install -y python3-pip curl git ros-${ROS_DISTRO}-ament-cmake-clang-format qtbase5-dev qtdeclarative5-dev
RUN pip3 install kuksa_client
RUN pip install setuptools==58.2.0
RUN sh -c 'echo "deb [arch=amd64,arm64] http://repo.ros2.org/ubuntu/main `lsb_release -cs` main" > /etc/apt/sources.list.d/ros2-latest.list'
RUN curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc |  apt-key add -
RUN apt update
RUN apt install -y python3-colcon-common-extensions

WORKDIR /src
COPY . .
RUN git clone https://github.com/LikhithST/ros_tutorials.git --branch humble
RUN . /opt/ros/humble/setup.sh; colcon build

# Execution stage
FROM ros:humble-ros-core-jammy

# Set environment 
ENV width 10
ENV height 20
ENV x_coord 1
ENV y_coord 1
ENV angle 0

# Install packages
RUN apt update && apt install -y python3-pip qtbase5-dev
RUN pip3 install kuksa_client

# Copy artefacts from builder
COPY --from=builder /src/install /src/install
CMD . /src/install/setup.sh; . /opt/ros/humble/setup.sh; ros2 run turtlesim turtlesim_node -w ${width} -h ${height} -x ${x_coord} -y ${y_coord} -r ${angle}& ros2 run f2tenth_simulator talker
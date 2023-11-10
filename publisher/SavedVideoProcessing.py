import cv2
import numpy as np

import asyncio
import argparse
import logging
import os
from pathlib import Path

from kuksa_client.grpc import Datapoint
from kuksa_client.grpc import DataEntry
from kuksa_client.grpc import EntryUpdate
from kuksa_client.grpc import Field
from kuksa_client.grpc import VSSClientError
from kuksa_client.grpc.aio import VSSClient


def init_argparse() -> argparse.ArgumentParser:
    """This inits the argument parser for the CSV-provider."""
    parser = argparse.ArgumentParser(
        usage="-a [BROKER ADDRESS] -p [BROKER PORT] -f [FILE]",
        description="This provider writes the content of a csv file to a kuksa.val databroker",
    )
    environment = os.environ
    parser.add_argument(
        "-a",
        "--address",
        default=environment.get("KUKSA_DATA_BROKER_ADDR", "127.0.0.1"),
        help="This indicates the address of the kuksa.val databroker to connect to."
        " The default value is 127.0.0.1",
    )
    parser.add_argument(
        "-p",
        "--port",
        default=environment.get("KUKSA_DATA_BROKER_PORT", "55555"),
        help="This indicates the port of the kuksa.val databroker to connect to."
        " The default value is 55555",
        type=int,
    )
    parser.add_argument(
        "-l",
        "--log",
        default=environment.get("PROVIDER_LOG_LEVEL", "INFO"),
        help="This sets the logging level. The default value is WARNING.",
        choices={"INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"},
    )
    parser.add_argument(
        "--cacertificate",
        help="Specify the path to your CA.pem. If used provider will connect using TLS",
        nargs="?",
        default=None,
    )
    parser.add_argument(
        "--tls-server-name",
        help="TLS server name, may be needed if addressing a server by IP-name",
        nargs="?",
        default=None,
    )
    return parser


async def main():
    """the main function as entry point for the CSV-provider"""
    parser = init_argparse()
    args = parser.parse_args()
    numeric_value = getattr(logging, args.log.upper(), None)
    if args.cacertificate:
        root_path = Path(args.cacertificate)
    else:
        root_path = None
    if isinstance(numeric_value, int):
        logging.basicConfig(encoding="utf-8", level=numeric_value)
    try:
        async with VSSClient(
            args.address,
            args.port,
            root_certificates=root_path,
            tls_server_name=args.tls_server_name,
        ) as client:
            await vehicle_control(client)
    except VSSClientError:
        logging.error(
            "Could not connect to the kuksa.val databroker at %s:%s."
            " Make sure to set the correct connection details using --address and --port"
            " and that the kuksa.val databroker is running.",
            args.address,
            args.port,
        )


async def pub_value(client, rows):
    for row in rows:
        if row["field"] == "current":
            # print(row['field'])
            entry = DataEntry(
                row["signal"],
                value=Datapoint(value=row["value"]),
            )
            updates = (EntryUpdate(entry, (Field.VALUE,)),)
            logging.info(
                "Update current value of %s to %s", row["signal"], row["value"]
            )
        elif row["field"] == "target":
            # print(row['field'])
            entry = DataEntry(
                row["signal"], actuator_target=Datapoint(value=row["value"])
            )
            updates = (EntryUpdate(entry, (Field.ACTUATOR_TARGET,)),)
            logging.info("Update target value of %s to %s", row["signal"], row["value"])
        else:
            updates = []
        try:
            await client.set(updates=updates)
        except VSSClientError as ex:
            logging.error("Error while updating %s\n%s", row["signal"], ex)
        try:
            await asyncio.sleep(delay=float(row["delay"]))
        except ValueError:
            logging.error(
                "Error while waiting for %s seconds after updating %s to %s."
                " Make sure to only use numbers for the delay value.",
                row["delay"],
                row["signal"],
                row["value"],
            )


async def vehicle_control(client):
    # import RPi.GPIO as GPIO
    cap = cv2.VideoCapture("./video.mp4")
    cap.set(3, 160)
    cap.set(4, 120)
    while True:
        ret, frame = cap.read()
        low_b = np.uint8([236, 240, 235])
        high_b = np.uint8([0, 0, 0])
        mask = cv2.inRange(frame, high_b, low_b)
        contours, hierarchy = cv2.findContours(mask, 1, cv2.CHAIN_APPROX_NONE)
        cv2.imshow("Frame", frame)
        value = [
            {
                "field": "target",
                "signal": "Vehicle.Teleoperation.IsEnabled",
                "value": "TRUE",
                "delay": "0",
            },
            {
                "field": "target",
                "signal": "Vehicle.Powertrain.Transmission.ClutchEngagement",
                "value": "0",
                "delay": "0",
            },
            {
                "field": "target",
                "signal": "Vehicle.Powertrain.Transmission.SelectedGear",
                "value": "3",
                "delay": "0",
            },
            {
                "field": "target",
                "signal": "Vehicle.Teleoperation.Brake",
                "value": "0",
                "delay": "0",
            },
            {
                "field": "target",
                "signal": "Vehicle.Teleoperation.SteeringAngle",
                "value": "0",
                "delay": "0",
            },
            {
                "field": "target",
                "signal": "Vehicle.Teleoperation.Torque",
                "value": "0.7",
                "delay": "0",
            },
        ]
        await pub_value(client, value)
        if cv2.waitKey(1) & 0xFF == ord("q"):  # 1 is the time in ms
            break
    cap.release()
    cv2.destroyAllWindows()


asyncio.run(main())

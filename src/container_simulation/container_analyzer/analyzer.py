"""
Containerized System Analyzer

This module provides functionality for monitoring and analyzing the resource usage
of Docker containers and Swarm services. It collects CPU, RAM, Disk, and Network
statistics over a specified time window and computes average resource consumption.

Classes:
    - ContainerizedSystemAnalyzer: Monitors and analyzes container/service resource usage.

Functions:
    - parse_timestamp(timestamp: str) -> datetime: Parses and converts an ISO 8601 timestamp.
    - get_cpu_cores_used(stat: dict) -> float: Computes the number of CPU cores actively used.
    - get_ram_usage_mb(stat: dict) -> float: Retrieves RAM usage in MB.
    - get_total_network_usage(start_stat: dict, end_stat: dict) -> dict: Calculates network usage.
    - analyze_container_performance(container_or_service_id: Optional[str],
        container_or_service_name: Optional[str]) -> dict:
            Collects resource usage statistics over a time window and computes averages.

Usage Example:
    analyzer = ContainerizedSystemAnalyzer(time_window=20, period=0.1)
    result = analyzer.analyze_container_performance("0800b9b5426c")

    print(f"Average CPU Usage: {result['average_cpu_cores']} cores")
    print(f"Average RAM Usage: {result['average_ram_usage_mb']} MB")
    print(f"Average Disk Space Used: {result['average_disk_usage_mb']} MB")
    print(f"Total Network RX: {result['average_rx_mb']} MB")
    print(f"Total Network TX: {result['average_tx_mb']} MB")
"""

import time
import json
from typing import Optional
from datetime import datetime

from statistics import mean
from logging import Logger

from container_simulation.utils import get_logger
from container_simulation.container_analyzer.container_analyzer import ContainerAnalyzer
from container_simulation.container_analyzer.service_analyzer import ServiceAnalyzer

LOGGER: Logger = get_logger()


class ContainerizedSystemAnalyzer:
    """
    Analyzes resource consumption of Docker containers or
    Swarm services over a specified time window.
    This class collects CPU, RAM, Disk, and Network usage statistics and computes averages.

    Attributes:
        time_window (int): The total duration (in seconds) for monitoring.
        period (float): The interval (in seconds) between each measurement.
            IMPORTANT: The measurement takes time and if the period value is too low then it
                won't be applied as expected (Just a sleep will be included after the measurement)
        entries (list[str]): A list of resource metrics to monitor (e.g., "cpu", "ram", "disk"...).
        analyzer (ContainerAnalyzer | ServiceAnalyzer):
            The appropriate analyzer instance based on swarm mode.
    """

    def __init__(
        self,
        time_window: int = 20,
        period: float = 0.1,
        swarm_mode: bool = False,
        entries: Optional[list[str]] = None,
    ) -> None:
        """
        Initializes the containerized system analyzer.

        Args:
            time_window (int, optional): Duration (in seconds) to monitor
                the container/service.
            period (float, optional): Sampling interval (in seconds) between measurements.
            swarm_mode (bool, optional): Whether to analyze a Swarm service instead of a container.
            entries (Optional[list[str]], optional): List of metrics to track
                (default: ["cpu", "ram", "disk", "bw"]).
        """
        self.time_window: int = time_window
        self.period: float = period
        self.entries: list[str] = entries or ["cpu", "ram", "disk", "bw"]
        if swarm_mode:
            self.analyzer: ServiceAnalyzer = ServiceAnalyzer()
        else:
            self.analyzer: ContainerAnalyzer = ContainerAnalyzer()

    @staticmethod
    def parse_timestamp(timestamp: str) -> datetime:
        """
        Parses an ISO 8601 timestamp and converts it to a datetime object.
        Handles nanoseconds by truncating them to microseconds.

        Args:
            timestamp (str): The timestamp string in ISO 8601 format.

        Returns:
            datetime: Parsed datetime object.
        """
        timestamp: str = timestamp.rstrip("Z")  # Remove 'Z' if present
        parts: list[str] = timestamp.split(".")  # Split timestamp at decimal

        if len(parts) == 2 and len(parts[1]) > 6:
            # Convert nanoseconds to microseconds by truncating extra digits
            timestamp: str = f"{parts[0]}.{parts[1][:6]}"

        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")

    @staticmethod
    def get_cpu_cores_used(stat: dict) -> float:
        """
        Calculates the number of CPU cores actively used by the container or service.

        Args:
            stat (dict): The statistics dictionary retrieved from Docker.

        Returns:
            float: The number of CPU cores actively used.
        """
        precpu_stats: dict = stat["precpu_stats"]
        cpu_stats: dict = stat["cpu_stats"]

        total_usage_diff: float = (
            cpu_stats["cpu_usage"]["total_usage"] - precpu_stats["cpu_usage"]["total_usage"]
        )
        system_usage_diff: float = cpu_stats["system_cpu_usage"] - precpu_stats["system_cpu_usage"]
        online_cpus: float = cpu_stats["online_cpus"]

        return (
            round((total_usage_diff / system_usage_diff) * online_cpus, 4)
            if system_usage_diff > 0
            else 0.0
        )

    @staticmethod
    def get_ram_usage_mb(stat: dict) -> float:
        """
        Calculates the RAM usage of the container/service in megabytes (MB).

        Args:
            stat (dict): The statistics dictionary retrieved from Docker.

        Returns:
            float: RAM usage in MB.
        """
        memory_stats: dict = stat["memory_stats"]
        memory_usage: int = memory_stats["usage"]  # Bytes

        return round(memory_usage / (1024**2), 4)  # Convert to MB

    @staticmethod
    def get_total_network_usage(start_stat: dict, end_stat: dict) -> dict:
        """
        Computes the total network data used (MB) within the monitoring window.

        Args:
            start_stat (dict): Initial network statistics.
            end_stat (dict): Final network statistics.

        Returns:
            dict: A dictionary containing:
                - "total_rx_mb" (float): Total received data in MB.
                - "total_tx_mb" (float): Total transmitted data in MB.
        """
        networks_start: dict = start_stat.get("networks", {})
        networks_end: dict = end_stat.get("networks", {})

        if not networks_start or not networks_end:
            LOGGER.warning("No network data available. 0 (zero) will be used!")
            return {"total_rx_mb": 0.0, "total_tx_mb": 0.0}

        # Auto-detect the first available network interface
        network_interface: str = next(iter(networks_start), None)
        if not network_interface:
            LOGGER.warning("No network interfaces found. 0 (zero) will be used!")
            return {"total_rx_mb": 0.0, "total_tx_mb": 0.0}

        LOGGER.debug(f"DEBUG: Using network interface: {network_interface}")

        # Extract data
        rx_start: int = networks_start.get(network_interface, {}).get("rx_bytes", 0)
        tx_start: int = networks_start.get(network_interface, {}).get("tx_bytes", 0)
        rx_end: int = networks_end.get(network_interface, {}).get("rx_bytes", 0)
        tx_end: int = networks_end.get(network_interface, {}).get("tx_bytes", 0)

        LOGGER.debug(f"DEBUG: Network RX start: {rx_start} bytes, end: {rx_end} bytes")  # Debugging
        LOGGER.debug(f"DEBUG: Network TX start: {tx_start} bytes, end: {tx_end} bytes")  # Debugging

        total_rx: float = max(rx_end - rx_start, 0) / (1024**2)  # Convert bytes to MB
        total_tx: float = max(tx_end - tx_start, 0) / (1024**2)  # Convert bytes to MB

        return {
            "total_rx_mb": round(total_rx, 4),
            "total_tx_mb": round(total_tx, 4),
        }

    @staticmethod
    def get_mean_values(samples: dict) -> dict:
        """
        Computes the mean values from collected resource usage samples.

        Args:
            samples (dict): A dictionary containing resource usage samples.

        Returns:
            dict: A dictionary with entity-wise mean values.
        """
        return_structure: dict = {}
        tmp_structure: dict = {}

        for entity, ticks in samples.items():  # ticks is now the inner dict (time: value)
            if entity not in tmp_structure:
                tmp_structure[entity] = []

            for tick in ticks:  # Iterate over actual sample tick timestamps
                tmp_structure[entity].append(ticks[tick])

        # Compute the mean for each entity
        for entity in tmp_structure.keys():
            return_structure[entity] = round(mean(tmp_structure[entity]), 4)  # Proper mean

        return return_structure

    def analyze_container_performance(
        self,
        container_or_service_id: Optional[str] = None,
        container_or_service_name: Optional[str] = None,
        all_entity: bool = False,
        write_to_file: bool = False,
    ) -> dict:
        """
        Collects resource usage statistics for a Docker container or
        Swarm service over a time window.

        Args:
            container_or_service_id (Optional[str], optional): The container or service ID.
            container_or_service_name (Optional[str], optional): The container or service name.
            all_entity (bool): If True, analyzes all available Docker
                entities (containers, services).
            write_to_file (bool): If True, writes the collected analysis data to a JSON file.

        Returns:
            dict: A dictionary containing:
                - "mean_cpu_cores" (float): Mean CPU cores used.
                - "mean_ram_usage_mb" (float): Mean RAM usage in MB.
                - "mean_disk_usage_mb" (float): Mean disk usage in MB.
                - "mean_rx_mb" (float): Mean network received data in MB.
                - "mean_tx_mb" (float): Mean network transmitted data in MB.
                - "samples_cpu" (dict): CPU usage samples over time.
                - "samples_ram" (dict): RAM usage samples over time.
                - "samples_disk" (dict): Disk usage samples over time.
                - "samples_rx" (dict): Network RX samples over time.
                - "samples_tx" (dict): Network TX samples over time.
        """
        start_time: float = time.time()
        previous_stat, samples = self._initialize_sample_storage()
        analyze_entities = self._get_analyze_entities(
            container_or_service_id, container_or_service_name, all_entity
        )

        sample_tick: float = 0
        already_analyzed: list[str] = []

        while (time.time() - start_time) < self.time_window:
            self._collect_samples(
                analyze_entities, already_analyzed, previous_stat, samples, sample_tick
            )
            sample_tick += self.period
            time.sleep(self.period)

        if write_to_file:
            self._write_results_to_file(samples)

        return self._compute_results(samples)

    @staticmethod
    def _initialize_sample_storage() -> tuple[dict, dict]:
        """
        Initializes the storage dictionaries for previous stats and resource usage samples.

        Returns:
            tuple: A tuple containing:
                - previous_stat (dict): Stores previous statistical data for each entity.
                - samples (dict): Stores the collected CPU, RAM, Disk, and Network samples.
        """
        return {}, {
            "cpu_cores_samples": {},
            "ram_usage_samples": {},
            "disk_usage_samples": {},
            "rx_usage_samples": {},
            "tx_usage_samples": {},
        }

    def _get_analyze_entities(
        self,
        container_or_service_id: Optional[str],
        container_or_service_name: Optional[str],
        all_entity: bool,
    ) -> list:
        """
        Retrieves the list of entities to analyze.

        Args:
            container_or_service_id (Optional[str]): Container/service ID.
            container_or_service_name (Optional[str]): Container/service name.
            all_entity (bool): If True, retrieves all available entities.

        Returns:
            list: A list of container or service entities to analyze.
        """
        return (
            self.analyzer.get_entity()
            if all_entity
            else [
                self.analyzer.get_container_or_service_ref(
                    container_or_service_id, container_or_service_name
                )
            ]
        )

    def _collect_samples(
        self,
        analyze_entities: list,
        already_analyzed: list[str],
        previous_stat: dict,
        samples: dict,
        sample_tick: float,
    ) -> None:
        """
        Collects resource usage samples for all entities at a given time tick.

        Args:
            analyze_entities (list): List of entities to analyze.
            already_analyzed (list[str]): List of already analyzed entities.
            previous_stat (dict): Dictionary storing previous statistics for each entity.
            samples (dict): Dictionary containing collected samples.
            sample_tick (float): The current sample time tick.
        """
        for docker_entity in analyze_entities:
            docker_entity_name = docker_entity.name
            # TODO: Fix the timestamps. The tick usage is not OK.
            formatted_tick: str = "{:.2f}".format(sample_tick).rstrip("0").rstrip(".")

            if docker_entity_name not in already_analyzed:
                previous_stat[docker_entity_name] = self.analyzer.get_stats(name=docker_entity_name)
                self._initialize_entity_samples(samples, docker_entity_name)
                already_analyzed.append(docker_entity_name)

            current_stat: dict = self.analyzer.get_stats(name=docker_entity_name)

            self._update_samples(
                samples, docker_entity_name, formatted_tick, current_stat, previous_stat
            )

            previous_stat[docker_entity_name] = current_stat

    @staticmethod
    def _initialize_entity_samples(samples: dict, entity_name: str) -> None:
        """
        Initializes the sample dictionaries for a new entity.

        Args:
            samples (dict): Dictionary storing resource usage samples.
            entity_name (str): Name of the entity being analyzed.
        """
        samples["cpu_cores_samples"][entity_name] = {}
        samples["ram_usage_samples"][entity_name] = {}
        samples["disk_usage_samples"][entity_name] = {}
        samples["rx_usage_samples"][entity_name] = {}
        samples["tx_usage_samples"][entity_name] = {}

    def _update_samples(
        self,
        samples: dict,
        entity_name: str,
        formatted_tick: str,
        current_stat: dict,
        previous_stat: dict,
    ) -> None:
        """
        Updates the resource usage samples for a given entity at a specific time tick.

        Args:
            samples (dict): Dictionary storing collected samples.
            entity_name (str): The name of the entity being analyzed.
            formatted_tick (str): The formatted sample tick.
            current_stat (dict): The current statistics of the entity.
            previous_stat (dict): The previous statistics of the entity.
        """
        samples["cpu_cores_samples"][entity_name][formatted_tick] = self.get_cpu_cores_used(
            current_stat
        )
        samples["ram_usage_samples"][entity_name][formatted_tick] = self.get_ram_usage_mb(
            current_stat
        )
        samples["disk_usage_samples"][entity_name][formatted_tick] = self.analyzer.get_disk_usage(
            container_or_service_name=entity_name
        )

        self._update_network_samples(
            samples, entity_name, formatted_tick, current_stat, previous_stat
        )

    @staticmethod
    def _update_network_samples(
        samples: dict,
        entity_name: str,
        formatted_tick: str,
        current_stat: dict,
        previous_stat: dict,
    ) -> None:
        """
        Updates network-related samples for a given entity.

        Args:
            samples (dict): Dictionary storing collected samples.
            entity_name (str): The name of the entity being analyzed.
            formatted_tick (str): The formatted sample tick.
            current_stat (dict): The current statistics of the entity.
            previous_stat (dict): The previous statistics of the entity.
        """
        networks_current = current_stat.get("networks", {})
        networks_previous = previous_stat[entity_name].get("networks", {})

        network_interface: str = next(iter(networks_current), None)

        if network_interface and network_interface in networks_previous:
            rx_now = networks_current[network_interface].get("rx_bytes", 0)
            tx_now = networks_current[network_interface].get("tx_bytes", 0)

            rx_prev = networks_previous[network_interface].get("rx_bytes", 0)
            tx_prev = networks_previous[network_interface].get("tx_bytes", 0)

            samples["rx_usage_samples"][entity_name][formatted_tick] = max(rx_now - rx_prev, 0) / (
                1024**2
            )  # MB
            samples["tx_usage_samples"][entity_name][formatted_tick] = max(tx_now - tx_prev, 0) / (
                1024**2
            )  # MB

    @staticmethod
    def _write_results_to_file(samples: dict) -> None:
        """
        Writes collected sample data to a JSON file.

        Args:
            samples (dict): The collected resource usage samples.
        """
        filename: str = f"container_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as opened_file:
            json.dump(samples, opened_file, indent=4)
        LOGGER.info(f"Results saved to {filename}")

    def _compute_results(self, samples: dict) -> dict:
        """
        Computes the mean resource usage values from the collected samples.

        Args:
            samples (dict): Dictionary storing collected resource usage samples.

        Returns:
            dict: Dictionary containing mean resource values and sample data.
        """
        return {
            "mean_cpu_cores": self.get_mean_values(samples["cpu_cores_samples"]),
            "mean_ram_usage_mb": self.get_mean_values(samples["ram_usage_samples"]),
            "mean_disk_usage_mb": self.get_mean_values(samples["disk_usage_samples"]),
            "mean_rx_mb": self.get_mean_values(samples["rx_usage_samples"]),
            "mean_tx_mb": self.get_mean_values(samples["tx_usage_samples"]),
            "samples_cpu": samples["cpu_cores_samples"],
            "samples_ram": samples["ram_usage_samples"],
            "samples_disk": samples["disk_usage_samples"],
            "samples_rx": samples["rx_usage_samples"],
            "samples_tx": samples["tx_usage_samples"],
        }


if __name__ == "__main__":
    analyzer = ContainerizedSystemAnalyzer(time_window=30, period=0.1)
    result = analyzer.analyze_container_performance(all_entity=True, write_to_file=True)

    print("FINISHED!")

    print(f"Average CPU Usage: {result['mean_cpu_cores']} cores")
    print(f"Average RAM Usage: {result['mean_ram_usage_mb']} MB")
    print(f"Average Disk Space Used: {result['mean_disk_usage_mb']} MB")
    print(f"Total Network RX: {result['mean_rx_mb']} MB")
    print(f"Total Network TX: {result['mean_tx_mb']} MB")

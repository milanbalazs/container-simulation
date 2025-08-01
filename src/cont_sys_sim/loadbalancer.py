"""Load Balancer Module.

This module defines a simple **First-Fit Reservations Load Balancer** for distributing workloads
to containers and assigning containers to Nodes. The load balancer
operates using a **First-Fit Reservations strategy**, where each workload is assigned to the
first available container or Node that meets its resource requirements.

Classes:
    - `FirstFitComponentLoadBalancer`: Abstract base class for First-Fit Load Balancers.
    - `FirstFitContainerLoadBalancer`: Assigns workloads to containers using the
      First-Fit strategy.
    - `FirstFitNodeLoadBalancer`: Assigns containers to Nodes using the First-Fit strategy.

Example:
    >>> from cont_sys_sim.workload_request import WorkloadRequest
    >>> from cont_sys_sim.container import Container
    >>> from cont_sys_sim.node import Node
    >>> from cont_sys_sim.load_balancer import FirstFitReservationContainerLoadBalancer
    >>> workload1 = WorkloadRequest(cpu=2.0, ram=1024, disk=10, bw=100, delay=1, duration=5,
                                    cpu_fluctuation_percent=10.0, ram_fluctuation_percent=5.0,
                                    disk_fluctuation_percent=1.5, bw_fluctuation_percent=0.5,
                                    priority=1, workload_type="User Request")
    >>> container1 = Container(env, "AppContainer1", cpu=4, ram=4096, disk=100, bw=1000)
    >>> container2 = Container(env, "AppContainer2", cpu=2, ram=2048, disk=50, bw=500)
    >>> lb = FirstFitReservationContainerLoadBalancer([workload1], [container1, container2])

Dependencies:
    - `cont_sys_sim.node.Node`
    - `cont_sys_sim.workload_request.WorkloadRequest`
    - `cont_sys_sim.container.Container`

Notes:
    - If no suitable container or Node is found, an error is raised.
    - Uses **First-Fit Reservations** allocation,
        which assigns workloads to the first suitable resource.
"""

import warnings
from abc import ABC
from logging import Logger
from typing import Optional

from cont_sys_sim.node import Node
from cont_sys_sim.workload_request import WorkloadRequest
from cont_sys_sim.container import Container
from cont_sys_sim.utils import get_logger  # Import singleton logger

# Issue a warning at runtime when the module is imported
warnings.warn(
    "The 'load_balancer' module is under development."
    "The proper working is not guaranteed!"
    "Its behavior may change in future updates!",
    category=UserWarning,
    stacklevel=2,
)


class FirstFitReservationComponentLoadBalancer(ABC):
    """Abstract base class for First-Fit with Reservations Load Balancers.

    This class serves as a generic **First-Fit Reservations Load Balancer**,
    allowing the distribution of workload units (either WorkloadRequests or Containers)
    across available runner units (either Containers or Nodes).

    This class allows First-Fit load balancing with the option to:
    - **Enable reservations** (tracks resource usage over time).
    - **Disable reservations** (uses classic First-Fit strategy).

    Attributes:
        _workload_units (list[WorkloadRequest] | list[Container]):
            List of workloads or containers to be assigned.
        _execution_units (list[Container] | list[Node]):
            List of containers or Nodes where workloads should be placed.
        _use_reservations (bool, optional):
            If `True`, tracks resource usage over time for future scheduling.
            If `False`, assigns workloads immediately using pure First-Fit.
            Defaults to `True`.
        _logger (Optional[Logger]): Logger object.
    """

    def __init__(
        self,
        workload_units: list[WorkloadRequest] | list[Container],
        execution_units: list[Container] | list[Node],
        use_reservations: bool = True,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initializes the First-Fit Reservations Load Balancer.

        Args:
            workload_units (list[WorkloadRequest] | list[Container]):
                List of workloads or containers.
            execution_units (list[Container] | list[Node]):
                List of available containers or Nodes.
            use_reservations (bool, optional):
                If `True`, tracks resource usage over time for future scheduling.
                If `False`, assigns workloads immediately using pure First-Fit.
                Defaults to `True`.
            logger (Optional[Logger]): Logger object.
        """

        self._workload_units: list[WorkloadRequest] | list[Container] = workload_units
        self._execution_units: list[Container] | list[Node] = execution_units
        self._use_reservations: bool = use_reservations
        self._logger = logger if logger else get_logger()

    @staticmethod
    def is_suitable_runner(workload_unit, execution_unit) -> bool:
        """Checks if a given runner unit (Container/Node) can accommodate a workload.

        A runner unit is considered suitable if it has enough available CPU, RAM, Disk,
        and Bandwidth to accommodate the workload.

        Args:
            workload_unit (WorkloadRequest | Container): The workload or container to be assigned.
            execution_unit (Container | Node): The container or Node to check.

        Returns:
            bool: `True` if the runner unit has sufficient resources, `False` otherwise.
        """

        if (
            workload_unit.ram <= execution_unit.available_ram
            and workload_unit.cpu <= execution_unit.available_cpu
            and workload_unit.disk <= execution_unit.available_disk
            and workload_unit.bw <= execution_unit.available_bw
        ):
            return True
        return False

    def can_accommodate_workload(
        self, execution_unit, workload, start_time, end_time, forecast
    ) -> bool:
        """Checks if a workload can be accommodated in a runner (Container/Node) at a given time.

        This method considers a workload’s `delay` and `duration` to ensure the execution unit
        has enough resources available at **each time step** during execution.

        - If `use_reservations=True`, checks if resources will be available **at every time step**.
        - If `use_reservations=False`, uses classic First-Fit and checks only **current resources**.

        Args:
            execution_unit (Container | Node): The container or Node being evaluated.
            workload (WorkloadRequest | Container): The workload to be assigned.
            start_time (float): The time the workload starts execution.
            end_time (float): The time the workload finishes execution.
            forecast (dict): Forecasted resource usage for each execution unit over time.

        Returns:
            bool: `True` if the execution unit can accommodate the workload at all time steps,
                `False` otherwise.
        """

        # Skip time-based reservation logic if use_reservations is disabled (Pure First-Fit)
        if not self._use_reservations:
            return self.is_suitable_runner(workload, execution_unit)

        for time in range(int(start_time), int(end_time) + 1):
            expected_cpu = forecast[execution_unit].get(time, {}).get("cpu", 0) + workload.cpu
            expected_ram = forecast[execution_unit].get(time, {}).get("ram", 0) + workload.ram
            expected_disk = forecast[execution_unit].get(time, {}).get("disk", 0) + workload.disk
            expected_bw = forecast[execution_unit].get(time, {}).get("bw", 0) + workload.bw

            if (
                expected_cpu > execution_unit.cpu
                or expected_ram > execution_unit.ram
                or expected_disk > execution_unit.disk
                or expected_bw > execution_unit.bw
            ):
                return False  # Not enough resources available at this time

        return True  # Execution unit can handle the workload in the given timeframe

    def update_forecast(self, execution_unit, workload, start_time, end_time, forecast) -> None:
        """Updates the execution unit's resource usage forecast after assigning a workload.

        This ensures that future resource allocations consider assigned workloads.

        - If `use_reservations=True`, tracks future resource allocation.
        - If `use_reservations=False`, skips resource tracking.

        Args:
            execution_unit (Container | Node): The container or Node receiving the workload.
            workload (WorkloadRequest | Container): The workload being assigned.
            start_time (float): The time the workload starts execution.
            end_time (float): The time the workload finishes execution.
            forecast (dict): Forecasted resource usage for each execution unit over time.
        """

        # Skip reservation tracking if use_reservations is disabled
        if not self._use_reservations:
            return

        for time in range(int(start_time), int(end_time) + 1):
            if time not in forecast[execution_unit]:
                forecast[execution_unit][time] = {"cpu": 0, "ram": 0, "disk": 0, "bw": 0}

            forecast[execution_unit][time]["cpu"] += workload.cpu
            forecast[execution_unit][time]["ram"] += workload.ram
            forecast[execution_unit][time]["disk"] += workload.disk
            forecast[execution_unit][time]["bw"] += workload.bw

    @property
    def workload_units(self) -> list[WorkloadRequest] | list[Container]:
        """Gets the list of workload units to be assigned.

        This property returns the current list of workload units, which can either be
        `WorkloadRequest` instances (for Workload-to-Container balancing) or `Container`
        instances (for Container-to-Node balancing).

        Returns:
            list[WorkloadRequest] | list[Container]: The list of workload units to be balanced.
        """
        return self._workload_units

    @workload_units.setter
    def workload_units(self, new_workload_units: list[WorkloadRequest] | list[Container]) -> None:
        """Sets a new list of workload units.

        This property updates the list of workload units that need to be assigned.

        Args:
            new_workload_units (list[WorkloadRequest] | list[Container]):
                A new list of workload units to be assigned.
        """
        self._workload_units = new_workload_units

    @property
    def execution_units(self) -> list[Container] | list[Node]:
        """Gets the list of runner units (Containers or Nodes) for workload assignment.

        This property returns the available runner units, which can either be `Container`
        instances (for Workload-to-Container balancing) or `Node` instances (for
        Container-to-Node balancing).

        Returns:
            list[Container] | list[Node]: The list of available runner units.
        """
        return self._execution_units

    @execution_units.setter
    def execution_units(self, new_execution_units: list[Container] | list[Node]) -> None:
        """Sets a new list of runner units.

        This property updates the list of available runner units that will receive workloads.

        Args:
            new_execution_units (list[Container] | list[Node]):
                A new list of runner units (containers or Nodes).
        """
        self._execution_units = new_execution_units

    @property
    def logger(self) -> Logger:
        """Gets the logger of the execution unit.

        Returns:
            str: The logger of the execution unit.
        """
        return self._logger

    @logger.setter
    def logger(self, new_logger: Logger) -> None:
        """Sets a logger name for the execution unit.

        Args:
            new_logger (str): The new logger to be assigned.
        """
        self._logger = new_logger


class FirstFitReservationContainerLoadBalancer(FirstFitReservationComponentLoadBalancer):
    """First-Fit Reservations Load Balancer for assigning workloads to containers.

    This class assigns `WorkloadRequest` instances to the first available `Container`
    that meets the resource requirements (CPU, RAM, Disk, Bandwidth).

    Attributes:
        _workload_reqs (list[WorkloadRequest]): List of workloads to be assigned.
        _containers (list[Container]): List of available containers.
    """

    def __init__(
        self,
        workload_reqs: list[WorkloadRequest],
        containers: list[Container],
        use_reservations: bool = True,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initializes the First-Fit Reservations Container Load Balancer.

        Args:
            workload_reqs (list[WorkloadRequest]): List of workloads to be assigned.
            containers (list[Container]): List of available containers for assignment.
            use_reservations (bool, optional):
                If `True`, tracks resource usage over time for future scheduling.
                If `False`, assigns workloads immediately using pure First-Fit.
                Defaults to `True`.
        """

        self._workload_reqs: list[WorkloadRequest] = workload_reqs
        self._containers: list[Container] = containers

        super().__init__(
            workload_reqs, containers, use_reservations=use_reservations, logger=logger
        )

        self.assign_workload_req_to_container()

    def assign_workload_req_to_container(self) -> None:
        """Assigns workloads to containers using the First-Fit Reservations strategy.

        Iterates through the list of workloads and assigns each workload to the first
        available container that has sufficient resources. If no suitable container is
        found, an error is raised.

        Raises:
            RuntimeError: If no suitable container is available for a workload.
        """

        # Track expected resource utilization over time
        container_resource_forecast: dict[Container, dict] = {
            container: {} for container in self._containers
        }

        for workload_req in self._workload_reqs:
            assigned: bool = False

            for container in self._containers:
                start_time: float = workload_req.delay
                end_time: float = start_time + workload_req.duration

                if self.can_accommodate_workload(
                    container, workload_req, start_time, end_time, container_resource_forecast
                ):
                    self._logger.info(
                        f"[{container.env.now}] {workload_req.id} "
                        f"({workload_req.workload_type}) workload "
                        f"assigned to {container.name} container."
                    )
                    # Directly mark workload as "active" and handle forecast updates
                    self.update_forecast(
                        container, workload_req, start_time, end_time, container_resource_forecast
                    )
                    # Explicitly attach the workload without triggering redundant logic
                    if container.env.now not in container.workload_requests:
                        container.workload_requests[container.env.now] = []
                    container.workload_requests[container.env.now].append(workload_req)
                    assigned = True
                    break

            if not assigned:
                raise RuntimeError(
                    f"[LB] - No suitable container found for '{workload_req.workload_type}' "
                    f"at time {workload_req.delay}."
                )


class FirstFitReservationNodeLoadBalancer(FirstFitReservationComponentLoadBalancer):
    """First-Fit Reservations Load Balancer for assigning containers to Nodes.

    This class assigns `Container` instances to the first available `Node` that has
    sufficient resources.

    Attributes:
        _containers (list[Container]): List of containers to be assigned.
        _nodes (list[Node]): List of available Nodes.
    """

    def __init__(
        self, containers: list[Container], nodes: list[Node], use_reservations: bool = True
    ) -> None:
        """Initializes the First-Fit Reservations Node Load Balancer.

        Args:
            containers (list[Container]): List of containers to be assigned to Nodes.
            nodes (list[Node]): List of available Nodes for assignment.
            use_reservations (bool, optional):
                If `True`, tracks resource usage over time for future scheduling.
                If `False`, assigns workloads immediately using pure First-Fit.
                Defaults to `True`.
        """

        self._containers: list[Container] = containers
        self._nodes: list[Node] = nodes

        super().__init__(containers, nodes, use_reservations=use_reservations)

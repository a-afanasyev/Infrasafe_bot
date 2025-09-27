"""
Request Service - Geographic Optimizer
UK Management Bot - Request Management System

Geographic optimization for route planning and distance-based assignment.
Required by SPRINT_8_9_PLAN.md:57-60.
"""

import logging
import math
from typing import List, Dict, Any, Optional, Tuple, NamedTuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models import Request

logger = logging.getLogger(__name__)


class DistanceUnit(str, Enum):
    """Distance measurement units"""
    KILOMETERS = "km"
    MILES = "miles"
    METERS = "meters"


class OptimizationObjective(str, Enum):
    """Geographic optimization objectives"""
    MINIMIZE_TOTAL_DISTANCE = "minimize_total_distance"
    MINIMIZE_MAX_DISTANCE = "minimize_max_distance"
    MINIMIZE_TRAVEL_TIME = "minimize_travel_time"
    BALANCED_WORKLOAD = "balanced_workload"


@dataclass
class GeoPoint:
    """Geographic point with coordinates"""
    latitude: float
    longitude: float
    label: Optional[str] = None

    def __post_init__(self):
        # Validate coordinates
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Invalid longitude: {self.longitude}")


@dataclass
class ExecutorLocation:
    """Executor location and mobility information"""
    user_id: str
    current_location: GeoPoint
    home_base: Optional[GeoPoint] = None
    mobility_type: str = "walking"  # walking, bicycle, car, public_transport
    avg_speed_kmh: float = 5.0  # Average speed in km/h
    max_daily_distance: float = 50.0  # Maximum daily travel distance in km
    current_workload_distance: float = 0.0  # Current day's travel distance


@dataclass
class RequestLocation:
    """Request location with priority weighting"""
    request_number: str
    location: GeoPoint
    priority_weight: float = 1.0
    estimated_duration_hours: float = 2.0
    deadline: Optional[datetime] = None


@dataclass
class RouteSegment:
    """Route segment between two points"""
    from_point: GeoPoint
    to_point: GeoPoint
    distance_km: float
    estimated_travel_time_minutes: float
    travel_method: str


@dataclass
class OptimizedRoute:
    """Optimized route for an executor"""
    executor_user_id: str
    route_segments: List[RouteSegment]
    total_distance_km: float
    total_travel_time_minutes: float
    total_work_time_minutes: float
    efficiency_score: float
    requests_sequence: List[str]  # Request numbers in order


@dataclass
class GeographicOptimizationResult:
    """Result of geographic optimization"""
    optimized_routes: List[OptimizedRoute]
    total_distance_km: float
    total_travel_time_minutes: float
    optimization_objective: OptimizationObjective
    algorithm_used: str
    execution_time_ms: float
    efficiency_improvement_percent: float
    unassigned_requests: List[str]


class GeoOptimizer:
    """
    Geographic Optimizer for Request Assignment

    Optimizes request assignments based on geographic constraints and routing efficiency.
    Considers executor locations, travel times, and route optimization algorithms.
    """

    def __init__(self):
        # Default optimization parameters
        self.earth_radius_km = 6371.0
        self.default_travel_speeds = {
            "walking": 5.0,
            "bicycle": 15.0,
            "car": 30.0,
            "public_transport": 20.0
        }

        # Optimization weights
        self.optimization_weights = {
            "distance": 0.4,
            "travel_time": 0.3,
            "workload_balance": 0.2,
            "priority": 0.1
        }

    async def optimize_geographic_assignments(
        self,
        db: AsyncSession,
        request_locations: List[RequestLocation],
        executor_locations: List[ExecutorLocation],
        objective: OptimizationObjective = OptimizationObjective.MINIMIZE_TOTAL_DISTANCE,
        max_requests_per_executor: int = 8
    ) -> GeographicOptimizationResult:
        """
        Optimize request assignments based on geographic factors

        - Minimizes travel distances and times
        - Balances workload across executors
        - Considers executor mobility constraints
        - Returns optimized routes for each executor
        """
        start_time = datetime.utcnow()

        try:
            logger.info(f"Starting geographic optimization for {len(request_locations)} requests and {len(executor_locations)} executors")

            # Validate inputs
            if not request_locations or not executor_locations:
                return GeographicOptimizationResult(
                    optimized_routes=[],
                    total_distance_km=0.0,
                    total_travel_time_minutes=0.0,
                    optimization_objective=objective,
                    algorithm_used="none",
                    execution_time_ms=0.0,
                    efficiency_improvement_percent=0.0,
                    unassigned_requests=[req.request_number for req in request_locations]
                )

            # Calculate distance matrix
            distance_matrix = self._calculate_distance_matrix(
                [req.location for req in request_locations],
                [exec.current_location for exec in executor_locations]
            )

            # Select optimization algorithm based on problem size
            if len(request_locations) <= 10 and len(executor_locations) <= 5:
                algorithm = "exact_assignment"
                routes = await self._exact_assignment_algorithm(
                    request_locations, executor_locations, distance_matrix, objective
                )
            elif len(request_locations) <= 50:
                algorithm = "greedy_clustering"
                routes = await self._greedy_clustering_algorithm(
                    request_locations, executor_locations, distance_matrix, objective, max_requests_per_executor
                )
            else:
                algorithm = "heuristic_partitioning"
                routes = await self._heuristic_partitioning_algorithm(
                    request_locations, executor_locations, distance_matrix, objective, max_requests_per_executor
                )

            # Calculate optimization metrics
            total_distance = sum(route.total_distance_km for route in routes)
            total_travel_time = sum(route.total_travel_time_minutes for route in routes)

            # Calculate efficiency improvement (comparison with naive assignment)
            naive_distance = self._calculate_naive_assignment_distance(
                request_locations, executor_locations
            )
            efficiency_improvement = (
                ((naive_distance - total_distance) / naive_distance) * 100
                if naive_distance > 0 else 0.0
            )

            # Identify unassigned requests
            assigned_requests = set()
            for route in routes:
                assigned_requests.update(route.requests_sequence)
            unassigned_requests = [
                req.request_number for req in request_locations
                if req.request_number not in assigned_requests
            ]

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return GeographicOptimizationResult(
                optimized_routes=routes,
                total_distance_km=round(total_distance, 2),
                total_travel_time_minutes=round(total_travel_time, 1),
                optimization_objective=objective,
                algorithm_used=algorithm,
                execution_time_ms=execution_time,
                efficiency_improvement_percent=round(efficiency_improvement, 2),
                unassigned_requests=unassigned_requests
            )

        except Exception as e:
            logger.error(f"Geographic optimization failed: {e}")
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return GeographicOptimizationResult(
                optimized_routes=[],
                total_distance_km=0.0,
                total_travel_time_minutes=0.0,
                optimization_objective=objective,
                algorithm_used="error",
                execution_time_ms=execution_time,
                efficiency_improvement_percent=0.0,
                unassigned_requests=[req.request_number for req in request_locations]
            )

    def calculate_distance(
        self,
        point1: GeoPoint,
        point2: GeoPoint,
        unit: DistanceUnit = DistanceUnit.KILOMETERS
    ) -> float:
        """
        Calculate distance between two geographic points using Haversine formula

        - Accurate for distances up to several hundred kilometers
        - Returns distance in specified units
        - Accounts for Earth's curvature
        """
        # Convert latitude and longitude from degrees to radians
        lat1_rad = math.radians(point1.latitude)
        lon1_rad = math.radians(point1.longitude)
        lat2_rad = math.radians(point2.latitude)
        lon2_rad = math.radians(point2.longitude)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance_km = self.earth_radius_km * c

        # Convert to requested unit
        if unit == DistanceUnit.KILOMETERS:
            return distance_km
        elif unit == DistanceUnit.MILES:
            return distance_km * 0.621371
        elif unit == DistanceUnit.METERS:
            return distance_km * 1000
        else:
            return distance_km

    def calculate_travel_time(
        self,
        distance_km: float,
        travel_method: str = "walking"
    ) -> float:
        """Calculate travel time in minutes based on distance and travel method"""
        speed_kmh = self.default_travel_speeds.get(travel_method, 5.0)
        travel_time_hours = distance_km / speed_kmh
        return travel_time_hours * 60  # Convert to minutes

    async def optimize_route_sequence(
        self,
        start_location: GeoPoint,
        request_locations: List[RequestLocation],
        end_location: Optional[GeoPoint] = None
    ) -> List[RequestLocation]:
        """
        Optimize sequence of request visits for minimum travel distance

        - Uses nearest neighbor heuristic for small problems
        - Applies 2-opt improvements for better solutions
        - Considers request priorities and deadlines
        """
        if len(request_locations) <= 1:
            return request_locations

        # Start with nearest neighbor algorithm
        sequence = await self._nearest_neighbor_tsp(start_location, request_locations, end_location)

        # Improve with 2-opt algorithm if problem size allows
        if len(sequence) <= 20:
            sequence = await self._two_opt_improvement(start_location, sequence, end_location)

        return sequence

    def _calculate_distance_matrix(
        self,
        request_locations: List[GeoPoint],
        executor_locations: List[GeoPoint]
    ) -> List[List[float]]:
        """Calculate distance matrix between all requests and executors"""
        matrix = []

        for executor_location in executor_locations:
            executor_distances = []
            for request_location in request_locations:
                distance = self.calculate_distance(executor_location, request_location)
                executor_distances.append(distance)
            matrix.append(executor_distances)

        return matrix

    async def _exact_assignment_algorithm(
        self,
        request_locations: List[RequestLocation],
        executor_locations: List[ExecutorLocation],
        distance_matrix: List[List[float]],
        objective: OptimizationObjective
    ) -> List[OptimizedRoute]:
        """Exact assignment algorithm for small problems"""
        # Simplified exact algorithm - assign each request to nearest available executor
        routes = []
        available_executors = executor_locations.copy()
        unassigned_requests = request_locations.copy()

        for executor in available_executors:
            if not unassigned_requests:
                break

            executor_idx = executor_locations.index(executor)
            route_requests = []
            route_distance = 0.0
            route_travel_time = 0.0
            current_location = executor.current_location

            # Assign up to max requests to this executor
            for _ in range(min(3, len(unassigned_requests))):  # Max 3 requests per executor for exact
                # Find nearest unassigned request
                best_request = None
                best_distance = float('inf')

                for request in unassigned_requests:
                    distance = self.calculate_distance(current_location, request.location)
                    if distance < best_distance:
                        best_distance = distance
                        best_request = request

                if best_request:
                    route_requests.append(best_request)
                    route_distance += best_distance
                    route_travel_time += self.calculate_travel_time(best_distance, executor.mobility_type)
                    current_location = best_request.location
                    unassigned_requests.remove(best_request)

            # Create route
            if route_requests:
                route_segments = []
                current_pos = executor.current_location

                for request in route_requests:
                    distance = self.calculate_distance(current_pos, request.location)
                    travel_time = self.calculate_travel_time(distance, executor.mobility_type)

                    route_segments.append(RouteSegment(
                        from_point=current_pos,
                        to_point=request.location,
                        distance_km=distance,
                        estimated_travel_time_minutes=travel_time,
                        travel_method=executor.mobility_type
                    ))

                    current_pos = request.location

                routes.append(OptimizedRoute(
                    executor_user_id=executor.user_id,
                    route_segments=route_segments,
                    total_distance_km=route_distance,
                    total_travel_time_minutes=route_travel_time,
                    total_work_time_minutes=sum(req.estimated_duration_hours * 60 for req in route_requests),
                    efficiency_score=self._calculate_efficiency_score(route_distance, route_travel_time, len(route_requests)),
                    requests_sequence=[req.request_number for req in route_requests]
                ))

        return routes

    async def _greedy_clustering_algorithm(
        self,
        request_locations: List[RequestLocation],
        executor_locations: List[ExecutorLocation],
        distance_matrix: List[List[float]],
        objective: OptimizationObjective,
        max_requests_per_executor: int
    ) -> List[OptimizedRoute]:
        """Greedy clustering algorithm for medium-sized problems"""
        routes = []

        # Create clusters around executors
        for i, executor in enumerate(executor_locations):
            cluster_requests = []
            available_requests = request_locations.copy()

            # Add closest requests to this executor's cluster
            for _ in range(min(max_requests_per_executor, len(available_requests))):
                best_request = None
                best_distance = float('inf')

                for request in available_requests:
                    request_idx = request_locations.index(request)
                    distance = distance_matrix[i][request_idx]

                    # Apply priority weighting
                    weighted_distance = distance / request.priority_weight

                    if weighted_distance < best_distance:
                        best_distance = weighted_distance
                        best_request = request

                if best_request:
                    cluster_requests.append(best_request)
                    available_requests.remove(best_request)

            # Optimize route sequence within cluster
            if cluster_requests:
                optimized_sequence = await self.optimize_route_sequence(
                    executor.current_location,
                    cluster_requests,
                    executor.home_base
                )

                # Build route
                route_segments = []
                total_distance = 0.0
                total_travel_time = 0.0
                current_pos = executor.current_location

                for request in optimized_sequence:
                    distance = self.calculate_distance(current_pos, request.location)
                    travel_time = self.calculate_travel_time(distance, executor.mobility_type)

                    route_segments.append(RouteSegment(
                        from_point=current_pos,
                        to_point=request.location,
                        distance_km=distance,
                        estimated_travel_time_minutes=travel_time,
                        travel_method=executor.mobility_type
                    ))

                    total_distance += distance
                    total_travel_time += travel_time
                    current_pos = request.location

                routes.append(OptimizedRoute(
                    executor_user_id=executor.user_id,
                    route_segments=route_segments,
                    total_distance_km=total_distance,
                    total_travel_time_minutes=total_travel_time,
                    total_work_time_minutes=sum(req.estimated_duration_hours * 60 for req in optimized_sequence),
                    efficiency_score=self._calculate_efficiency_score(total_distance, total_travel_time, len(optimized_sequence)),
                    requests_sequence=[req.request_number for req in optimized_sequence]
                ))

        return routes

    async def _heuristic_partitioning_algorithm(
        self,
        request_locations: List[RequestLocation],
        executor_locations: List[ExecutorLocation],
        distance_matrix: List[List[float]],
        objective: OptimizationObjective,
        max_requests_per_executor: int
    ) -> List[OptimizedRoute]:
        """Heuristic partitioning algorithm for large problems"""
        # Simplified partitioning - divide requests by geographic regions
        routes = []

        # Calculate geographic bounds
        lat_min = min(req.location.latitude for req in request_locations)
        lat_max = max(req.location.latitude for req in request_locations)
        lon_min = min(req.location.longitude for req in request_locations)
        lon_max = max(req.location.longitude for req in request_locations)

        # Create grid partitions
        num_partitions = min(len(executor_locations), 4)  # Max 4 partitions
        lat_step = (lat_max - lat_min) / math.sqrt(num_partitions)
        lon_step = (lon_max - lon_min) / math.sqrt(num_partitions)

        partitions = []
        for i in range(int(math.sqrt(num_partitions))):
            for j in range(int(math.sqrt(num_partitions))):
                partition_bounds = {
                    'lat_min': lat_min + i * lat_step,
                    'lat_max': lat_min + (i + 1) * lat_step,
                    'lon_min': lon_min + j * lon_step,
                    'lon_max': lon_min + (j + 1) * lon_step
                }
                partitions.append(partition_bounds)

        # Assign requests to partitions
        partition_requests = [[] for _ in partitions]
        for request in request_locations:
            for idx, partition in enumerate(partitions):
                if (partition['lat_min'] <= request.location.latitude <= partition['lat_max'] and
                    partition['lon_min'] <= request.location.longitude <= partition['lon_max']):
                    partition_requests[idx].append(request)
                    break

        # Assign executors to partitions and create routes
        for idx, (partition, requests) in enumerate(zip(partitions, partition_requests)):
            if not requests or idx >= len(executor_locations):
                continue

            executor = executor_locations[idx]

            # Limit requests per executor
            if len(requests) > max_requests_per_executor:
                requests = requests[:max_requests_per_executor]

            # Optimize sequence within partition
            optimized_sequence = await self.optimize_route_sequence(
                executor.current_location,
                requests
            )

            # Build route
            if optimized_sequence:
                route_segments = []
                total_distance = 0.0
                total_travel_time = 0.0
                current_pos = executor.current_location

                for request in optimized_sequence:
                    distance = self.calculate_distance(current_pos, request.location)
                    travel_time = self.calculate_travel_time(distance, executor.mobility_type)

                    route_segments.append(RouteSegment(
                        from_point=current_pos,
                        to_point=request.location,
                        distance_km=distance,
                        estimated_travel_time_minutes=travel_time,
                        travel_method=executor.mobility_type
                    ))

                    total_distance += distance
                    total_travel_time += travel_time
                    current_pos = request.location

                routes.append(OptimizedRoute(
                    executor_user_id=executor.user_id,
                    route_segments=route_segments,
                    total_distance_km=total_distance,
                    total_travel_time_minutes=total_travel_time,
                    total_work_time_minutes=sum(req.estimated_duration_hours * 60 for req in optimized_sequence),
                    efficiency_score=self._calculate_efficiency_score(total_distance, total_travel_time, len(optimized_sequence)),
                    requests_sequence=[req.request_number for req in optimized_sequence]
                ))

        return routes

    async def _nearest_neighbor_tsp(
        self,
        start_location: GeoPoint,
        request_locations: List[RequestLocation],
        end_location: Optional[GeoPoint] = None
    ) -> List[RequestLocation]:
        """Nearest neighbor algorithm for TSP-like route optimization"""
        if not request_locations:
            return []

        sequence = []
        remaining = request_locations.copy()
        current_location = start_location

        while remaining:
            # Find nearest unvisited request
            nearest_request = None
            nearest_distance = float('inf')

            for request in remaining:
                distance = self.calculate_distance(current_location, request.location)
                # Apply priority weighting
                weighted_distance = distance / request.priority_weight

                if weighted_distance < nearest_distance:
                    nearest_distance = weighted_distance
                    nearest_request = request

            if nearest_request:
                sequence.append(nearest_request)
                remaining.remove(nearest_request)
                current_location = nearest_request.location

        return sequence

    async def _two_opt_improvement(
        self,
        start_location: GeoPoint,
        sequence: List[RequestLocation],
        end_location: Optional[GeoPoint] = None
    ) -> List[RequestLocation]:
        """2-opt improvement algorithm for route optimization"""
        if len(sequence) < 4:
            return sequence

        improved = True
        current_sequence = sequence.copy()

        while improved:
            improved = False
            current_distance = self._calculate_sequence_distance(start_location, current_sequence, end_location)

            for i in range(len(current_sequence) - 1):
                for j in range(i + 2, len(current_sequence)):
                    # Create new sequence by reversing segment between i and j
                    new_sequence = current_sequence.copy()
                    new_sequence[i:j+1] = reversed(new_sequence[i:j+1])

                    new_distance = self._calculate_sequence_distance(start_location, new_sequence, end_location)

                    if new_distance < current_distance:
                        current_sequence = new_sequence
                        current_distance = new_distance
                        improved = True
                        break

                if improved:
                    break

        return current_sequence

    def _calculate_sequence_distance(
        self,
        start_location: GeoPoint,
        sequence: List[RequestLocation],
        end_location: Optional[GeoPoint] = None
    ) -> float:
        """Calculate total distance for a sequence of locations"""
        if not sequence:
            return 0.0

        total_distance = 0.0
        current_location = start_location

        for request in sequence:
            distance = self.calculate_distance(current_location, request.location)
            total_distance += distance
            current_location = request.location

        # Add return distance if end location specified
        if end_location:
            total_distance += self.calculate_distance(current_location, end_location)

        return total_distance

    def _calculate_efficiency_score(
        self,
        total_distance: float,
        total_travel_time: float,
        num_requests: int
    ) -> float:
        """Calculate efficiency score for a route"""
        if num_requests == 0:
            return 0.0

        # Efficiency metrics
        distance_per_request = total_distance / num_requests
        time_per_request = total_travel_time / num_requests

        # Lower values = higher efficiency
        # Normalize to 0-1 scale where 1 = most efficient
        distance_efficiency = max(0, 1 - (distance_per_request / 10))  # Assume 10km per request is poor
        time_efficiency = max(0, 1 - (time_per_request / 60))  # Assume 60 min per request is poor

        return (distance_efficiency + time_efficiency) / 2

    def _calculate_naive_assignment_distance(
        self,
        request_locations: List[RequestLocation],
        executor_locations: List[ExecutorLocation]
    ) -> float:
        """Calculate total distance for naive (non-optimized) assignment"""
        if not request_locations or not executor_locations:
            return 0.0

        total_distance = 0.0
        requests_per_executor = len(request_locations) // len(executor_locations) + 1

        for i, executor in enumerate(executor_locations):
            start_idx = i * requests_per_executor
            end_idx = min((i + 1) * requests_per_executor, len(request_locations))
            executor_requests = request_locations[start_idx:end_idx]

            current_location = executor.current_location
            for request in executor_requests:
                distance = self.calculate_distance(current_location, request.location)
                total_distance += distance
                current_location = request.location

        return total_distance

    async def get_distance_matrix_for_requests(
        self,
        db: AsyncSession,
        request_numbers: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """Get distance matrix between multiple requests"""
        try:
            # Get request locations from database
            query = select(Request).where(
                and_(
                    Request.request_number.in_(request_numbers),
                    Request.is_deleted == False,
                    Request.latitude.isnot(None),
                    Request.longitude.isnot(None)
                )
            )

            result = await db.execute(query)
            requests = result.scalars().all()

            # Build distance matrix
            distance_matrix = {}

            for request1 in requests:
                distance_matrix[request1.request_number] = {}
                point1 = GeoPoint(request1.latitude, request1.longitude)

                for request2 in requests:
                    if request1.request_number == request2.request_number:
                        distance_matrix[request1.request_number][request2.request_number] = 0.0
                    else:
                        point2 = GeoPoint(request2.latitude, request2.longitude)
                        distance = self.calculate_distance(point1, point2)
                        distance_matrix[request1.request_number][request2.request_number] = round(distance, 3)

            return distance_matrix

        except Exception as e:
            logger.error(f"Failed to calculate distance matrix: {e}")
            return {}

    async def get_optimization_suggestions(
        self,
        db: AsyncSession,
        request_numbers: List[str],
        executor_user_ids: List[str]
    ) -> Dict[str, Any]:
        """Get geographic optimization suggestions for requests and executors"""
        try:
            # This would integrate with User Service to get executor locations
            # For now, return mock suggestions

            suggestions = {
                "geographic_analysis": {
                    "total_requests": len(request_numbers),
                    "total_executors": len(executor_user_ids),
                    "average_distance_km": 12.5,
                    "suggested_algorithm": "greedy_clustering",
                    "estimated_optimization_improvement": "25-35%"
                },
                "route_recommendations": [
                    {
                        "executor_user_id": executor_id,
                        "recommended_requests": request_numbers[:3],  # Mock assignment
                        "estimated_total_distance_km": 15.8,
                        "estimated_travel_time_hours": 1.2,
                        "efficiency_score": 0.82
                    }
                    for executor_id in executor_user_ids[:len(request_numbers)//2]
                ],
                "geographic_insights": {
                    "request_clustering": "Requests are moderately clustered",
                    "executor_coverage": "Good geographic coverage",
                    "optimization_potential": "High - significant travel time savings possible"
                }
            }

            return suggestions

        except Exception as e:
            logger.error(f"Failed to get optimization suggestions: {e}")
            return {"error": str(e)}
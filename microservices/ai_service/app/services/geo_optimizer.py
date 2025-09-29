# Geographic Optimization Service
# UK Management Bot - AI Service Stage 3

import asyncio
import logging
import math
import random
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


class GeoOptimizer:
    """
    Stage 3: Geographic optimization for assignment routing
    Implements distance calculations, route optimization, and geographic clustering
    """

    def __init__(self):
        self.is_enabled = True

        # Tashkent districts with approximate coordinates (lat, lon)
        self.district_coordinates = {
            "Чиланзар": (41.2856, 69.2034),
            "Юнусабад": (41.3265, 69.2891),
            "Мирзо-Улугбек": (41.3142, 69.2856),
            "Яшнабад": (41.2667, 69.2167),
            "Сергели": (41.2045, 69.2234),
            "Шайхантахур": (41.3058, 69.2542),
            "Олмазор": (41.3357, 69.2978),
            "Бектемир": (41.2089, 69.3367),
            "Учтепа": (41.2756, 69.1892),
            "Янгихаёт": (41.2123, 69.1234)
        }

        # Travel speeds (km/h) by transport type and time
        self.travel_speeds = {
            "car": {"normal": 25, "rush_hour": 15, "evening": 30},
            "motorcycle": {"normal": 35, "rush_hour": 25, "evening": 40},
            "public": {"normal": 20, "rush_hour": 12, "evening": 18}
        }

        # Time zones for rush hour calculations
        self.rush_hours = [(7, 9), (17, 19)]  # Morning and evening rush

        # Optimization parameters
        self.max_distance_km = 15  # Maximum reasonable distance
        self.max_assignments_per_executor = 8
        self.distance_weight = 0.3  # Weight in overall score

    def calculate_distance(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Calculate Haversine distance between two coordinates in kilometers"""
        lat1, lon1 = coord1
        lat2, lon2 = coord2

        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (math.sin(dlat/2)**2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))

        # Earth's radius in kilometers
        earth_radius = 6371
        distance = earth_radius * c

        return distance

    def get_district_distance(self, district1: str, district2: str) -> float:
        """Get distance between two districts in kilometers"""
        if district1 not in self.district_coordinates:
            logger.warning(f"Unknown district: {district1}")
            return 10.0  # Default distance

        if district2 not in self.district_coordinates:
            logger.warning(f"Unknown district: {district2}")
            return 10.0

        coord1 = self.district_coordinates[district1]
        coord2 = self.district_coordinates[district2]

        return self.calculate_distance(coord1, coord2)

    def calculate_travel_time(
        self,
        district1: str,
        district2: str,
        transport_type: str = "car",
        time_of_day: Optional[int] = None
    ) -> int:
        """Calculate travel time between districts in minutes"""
        distance = self.get_district_distance(district1, district2)

        if time_of_day is None:
            time_of_day = datetime.now().hour

        # Determine traffic conditions
        traffic_condition = "normal"
        for start_hour, end_hour in self.rush_hours:
            if start_hour <= time_of_day <= end_hour:
                traffic_condition = "rush_hour"
                break

        if traffic_condition == "normal" and time_of_day >= 20:
            traffic_condition = "evening"

        # Get travel speed
        speed = self.travel_speeds.get(transport_type, self.travel_speeds["car"])
        speed_kmh = speed.get(traffic_condition, speed["normal"])

        # Calculate time in minutes
        travel_time = (distance / speed_kmh) * 60

        # Add buffer time for parking, walking, etc.
        buffer_time = 5 + (distance * 2)  # 5-15 minutes depending on distance

        return int(travel_time + buffer_time)

    async def optimize_geographic_assignment(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Optimize assignment considering geographic constraints
        Returns list of optimized assignments
        """
        try:
            logger.info(f"Optimizing {len(requests)} requests for {len(executors)} executors")

            assignments = []

            for request in requests:
                request_district = self._extract_district_from_address(request.get("address", ""))

                # Calculate geographic scores for all executors
                executor_scores = []

                for executor in executors:
                    if not executor.get("is_available", True):
                        continue

                    executor_district = executor.get("district", "Чиланзар")

                    # Calculate distance and travel time
                    distance = self.get_district_distance(request_district, executor_district)
                    travel_time = self.calculate_travel_time(
                        request_district,
                        executor_district,
                        executor.get("transport_type", "car")
                    )

                    # Calculate geographic score (higher is better)
                    distance_score = max(0, 1 - (distance / self.max_distance_km))

                    # Bonus for same district
                    same_district_bonus = 0.2 if request_district == executor_district else 0

                    # Travel time penalty
                    time_penalty = min(0.3, travel_time / 120)  # Max 30% penalty for 2+ hours

                    geographic_score = distance_score + same_district_bonus - time_penalty
                    geographic_score = max(0.1, min(1.0, geographic_score))

                    executor_scores.append({
                        "executor": executor,
                        "distance_km": distance,
                        "travel_time_minutes": travel_time,
                        "geographic_score": geographic_score,
                        "same_district": request_district == executor_district
                    })

                # Sort by geographic score
                executor_scores.sort(key=lambda x: x["geographic_score"], reverse=True)

                if executor_scores:
                    best_match = executor_scores[0]

                    assignment = {
                        "request_id": request.get("request_number", "unknown"),
                        "executor_id": best_match["executor"]["executor_id"],
                        "algorithm": "geographic_optimization",
                        "distance_km": best_match["distance_km"],
                        "travel_time_minutes": best_match["travel_time_minutes"],
                        "geographic_score": best_match["geographic_score"],
                        "same_district": best_match["same_district"],
                        "optimization_factors": {
                            "distance_optimization": True,
                            "traffic_consideration": True,
                            "district_clustering": best_match["same_district"]
                        }
                    }

                    assignments.append(assignment)

                    logger.info(f"Request {request.get('request_number')} assigned to executor {best_match['executor']['executor_id']} "
                              f"(distance: {best_match['distance_km']:.1f}km, "
                              f"travel: {best_match['travel_time_minutes']}min)")
                else:
                    logger.warning(f"No suitable executor found for request {request.get('request_number')}")

            return assignments

        except Exception as e:
            logger.error(f"Geographic optimization failed: {e}")
            raise

    def _extract_district_from_address(self, address: str) -> str:
        """Extract district name from address string"""
        address_lower = address.lower()

        for district in self.district_coordinates.keys():
            if district.lower() in address_lower:
                return district

        # Default fallback
        return "Чиланзар"

    async def optimize_route(self, executor_id: int, assignments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Optimize route for executor with multiple assignments
        Using nearest neighbor TSP approximation
        """
        try:
            if len(assignments) <= 1:
                return {
                    "executor_id": executor_id,
                    "optimized_route": assignments,
                    "total_distance_km": 0,
                    "total_travel_time_minutes": 0,
                    "optimization_improvement": 0
                }

            # Extract districts from assignments
            districts = []
            for assignment in assignments:
                district = self._extract_district_from_address(assignment.get("address", ""))
                districts.append(district)

            # Calculate distance matrix
            n = len(districts)
            distance_matrix = [[0] * n for _ in range(n)]

            for i in range(n):
                for j in range(n):
                    if i != j:
                        distance_matrix[i][j] = self.get_district_distance(districts[i], districts[j])

            # Nearest neighbor TSP approximation
            unvisited = set(range(1, n))  # Start from first location
            route = [0]
            current = 0
            total_distance = 0

            while unvisited:
                nearest = min(unvisited, key=lambda x: distance_matrix[current][x])
                total_distance += distance_matrix[current][nearest]
                route.append(nearest)
                unvisited.remove(nearest)
                current = nearest

            # Reorder assignments according to optimized route
            optimized_assignments = [assignments[i] for i in route]

            # Calculate travel times
            total_travel_time = 0
            for i in range(len(route) - 1):
                travel_time = self.calculate_travel_time(districts[route[i]], districts[route[i + 1]])
                total_travel_time += travel_time

            # Calculate improvement (compare with random order)
            random_distance = sum(distance_matrix[i][j] for i, j in zip(route[:-1], route[1:]))
            original_distance = sum(distance_matrix[i][i+1] for i in range(n-1))
            improvement = max(0, (original_distance - random_distance) / original_distance * 100)

            return {
                "executor_id": executor_id,
                "optimized_route": optimized_assignments,
                "route_districts": [districts[i] for i in route],
                "total_distance_km": round(total_distance, 2),
                "total_travel_time_minutes": total_travel_time,
                "optimization_improvement": round(improvement, 1),
                "algorithm": "nearest_neighbor_tsp"
            }

        except Exception as e:
            logger.error(f"Route optimization failed for executor {executor_id}: {e}")
            return {
                "executor_id": executor_id,
                "optimized_route": assignments,
                "error": str(e)
            }

    async def cluster_requests_by_geography(self, requests: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Cluster requests by geographic proximity
        Returns dict with district as key and requests list as value
        """
        clusters = {}

        for request in requests:
            district = self._extract_district_from_address(request.get("address", ""))

            if district not in clusters:
                clusters[district] = []
            clusters[district].append(request)

        # Sort clusters by number of requests (largest first)
        sorted_clusters = dict(sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True))

        logger.info(f"Created {len(sorted_clusters)} geographic clusters: "
                   f"{[(k, len(v)) for k, v in sorted_clusters.items()]}")

        return sorted_clusters

    async def calculate_optimal_executor_positioning(self, historical_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze historical data to suggest optimal executor positioning
        """
        try:
            # Analyze request distribution by district
            district_demand = {}
            for request in historical_requests:
                district = self._extract_district_from_address(request.get("address", ""))
                district_demand[district] = district_demand.get(district, 0) + 1

            # Calculate demand density
            total_requests = sum(district_demand.values())
            district_percentages = {
                district: (count / total_requests * 100)
                for district, count in district_demand.items()
            }

            # Suggest executor distribution
            total_executors = 10  # Assume 10 executors available
            suggested_distribution = {}

            for district, percentage in district_percentages.items():
                suggested_count = max(1, round(total_executors * percentage / 100))
                suggested_distribution[district] = suggested_count

            # Calculate coverage metrics
            coverage_analysis = {}
            for district, coords in self.district_coordinates.items():
                nearby_districts = []
                for other_district, other_coords in self.district_coordinates.items():
                    if district != other_district:
                        distance = self.calculate_distance(coords, other_coords)
                        if distance <= 5.0:  # Within 5km
                            nearby_districts.append(other_district)

                coverage_analysis[district] = {
                    "nearby_districts": nearby_districts,
                    "coverage_radius_km": 5.0,
                    "demand_percentage": district_percentages.get(district, 0)
                }

            return {
                "demand_analysis": district_demand,
                "demand_percentages": district_percentages,
                "suggested_executor_distribution": suggested_distribution,
                "coverage_analysis": coverage_analysis,
                "optimization_recommendations": [
                    "Place more executors in high-demand districts",
                    "Ensure each district has at least one nearby executor",
                    "Consider mobile executors for coverage gaps",
                    "Adjust positioning based on time-of-day patterns"
                ]
            }

        except Exception as e:
            logger.error(f"Optimal positioning calculation failed: {e}")
            return {"error": str(e)}

    async def health_check(self) -> str:
        """Health check for Geographic Optimizer"""
        try:
            # Test distance calculation
            test_distance = self.get_district_distance("Чиланзар", "Юнусабад")

            if test_distance <= 0 or test_distance > 50:  # Reasonable bounds for Tashkent
                return "unhealthy: distance calculation failed"

            # Test travel time calculation
            test_travel_time = self.calculate_travel_time("Чиланзар", "Юнусабад")

            if test_travel_time <= 0 or test_travel_time > 180:  # Max 3 hours
                return "unhealthy: travel time calculation failed"

            return "healthy"

        except Exception as e:
            logger.error(f"Geographic Optimizer health check failed: {e}")
            return f"unhealthy: {str(e)}"
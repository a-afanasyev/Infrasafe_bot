# Advanced Assignment Optimization Algorithms
# UK Management Bot - AI Service Stage 3

import asyncio
import logging
import random
import math
import copy
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import numpy as np

from app.services.ml_pipeline import MLPipelineService
from app.services.geo_optimizer import GeoOptimizer

logger = logging.getLogger(__name__)


class AdvancedAssignmentOptimizer:
    """
    Stage 3: Advanced optimization algorithms for assignment optimization
    Implements Genetic Algorithm, Simulated Annealing, and Hybrid approaches
    """

    def __init__(self):
        self.ml_pipeline = MLPipelineService()
        self.geo_optimizer = GeoOptimizer()

        # Algorithm weights for multi-objective optimization
        self.weights = {
            "ml_success_probability": 0.35,  # ML prediction weight
            "geographic_efficiency": 0.25,   # Distance optimization
            "executor_workload": 0.20,       # Load balancing
            "executor_specialization": 0.15, # Skill matching
            "urgency_factor": 0.05          # Priority handling
        }

        # Genetic Algorithm parameters
        self.ga_config = {
            "population_size": 50,
            "generations": 100,
            "mutation_rate": 0.1,
            "crossover_rate": 0.8,
            "elite_size": 5
        }

        # Simulated Annealing parameters
        self.sa_config = {
            "initial_temperature": 1000.0,
            "cooling_rate": 0.95,
            "min_temperature": 0.1,
            "max_iterations": 1000
        }

    async def optimize_batch_assignments(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]],
        algorithm: str = "hybrid"
    ) -> Dict[str, Any]:
        """
        Optimize batch assignment using specified algorithm
        """
        try:
            start_time = datetime.now()

            if algorithm == "genetic":
                result = await self._genetic_algorithm_optimization(requests, executors)
            elif algorithm == "simulated_annealing":
                result = await self._simulated_annealing_optimization(requests, executors)
            elif algorithm == "hybrid":
                result = await self._hybrid_optimization(requests, executors)
            else:
                raise ValueError(f"Unknown algorithm: {algorithm}")

            processing_time = (datetime.now() - start_time).total_seconds()

            return {
                "algorithm": algorithm,
                "assignments": result["assignments"],
                "optimization_score": result["score"],
                "metrics": result.get("metrics", {}),
                "processing_time_seconds": round(processing_time, 3),
                "total_requests": len(requests),
                "assigned_requests": len(result["assignments"]),
                "optimization_details": result.get("details", {})
            }

        except Exception as e:
            logger.error(f"Batch optimization failed: {e}")
            raise

    async def _genetic_algorithm_optimization(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Genetic Algorithm for assignment optimization
        """
        logger.info("Starting Genetic Algorithm optimization")

        # Initialize population
        population = await self._create_initial_population(
            requests, executors, self.ga_config["population_size"]
        )

        best_solution = None
        best_score = -float('inf')
        generation_scores = []

        for generation in range(self.ga_config["generations"]):
            # Evaluate fitness for all individuals
            fitness_scores = []
            for individual in population:
                score = await self._evaluate_solution_fitness(individual, requests, executors)
                fitness_scores.append(score)

                if score > best_score:
                    best_score = score
                    best_solution = copy.deepcopy(individual)

            generation_scores.append(max(fitness_scores))

            # Selection (tournament selection)
            new_population = await self._tournament_selection(population, fitness_scores)

            # Crossover
            offspring = []
            for i in range(0, len(new_population) - 1, 2):
                if random.random() < self.ga_config["crossover_rate"]:
                    child1, child2 = await self._crossover(
                        new_population[i], new_population[i + 1], requests, executors
                    )
                    offspring.extend([child1, child2])
                else:
                    offspring.extend([new_population[i], new_population[i + 1]])

            # Mutation
            for individual in offspring:
                if random.random() < self.ga_config["mutation_rate"]:
                    await self._mutate(individual, requests, executors)

            # Elite preservation
            elite_indices = sorted(range(len(fitness_scores)),
                                 key=lambda x: fitness_scores[x], reverse=True)[:self.ga_config["elite_size"]]
            elite = [population[i] for i in elite_indices]

            # New population
            population = elite + offspring[:self.ga_config["population_size"] - len(elite)]

            if generation % 20 == 0:
                logger.info(f"Generation {generation}: Best score = {best_score:.4f}")

        assignments = await self._convert_solution_to_assignments(best_solution, requests, executors)

        return {
            "assignments": assignments,
            "score": best_score,
            "metrics": {
                "generations": self.ga_config["generations"],
                "final_population_size": len(population),
                "convergence_scores": generation_scores[-10:]  # Last 10 generations
            },
            "details": {
                "algorithm": "genetic_algorithm",
                "best_solution": best_solution
            }
        }

    async def _simulated_annealing_optimization(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Simulated Annealing for assignment optimization
        """
        logger.info("Starting Simulated Annealing optimization")

        # Initialize with random solution
        current_solution = await self._create_random_solution(requests, executors)
        current_score = await self._evaluate_solution_fitness(current_solution, requests, executors)

        best_solution = copy.deepcopy(current_solution)
        best_score = current_score

        temperature = self.sa_config["initial_temperature"]
        iteration_scores = []

        for iteration in range(self.sa_config["max_iterations"]):
            # Generate neighbor solution
            neighbor_solution = await self._generate_neighbor_solution(
                current_solution, requests, executors
            )
            neighbor_score = await self._evaluate_solution_fitness(
                neighbor_solution, requests, executors
            )

            # Accept or reject neighbor
            if neighbor_score > current_score:
                # Better solution - accept
                current_solution = neighbor_solution
                current_score = neighbor_score

                if current_score > best_score:
                    best_solution = copy.deepcopy(current_solution)
                    best_score = current_score
            else:
                # Worse solution - accept with probability
                delta = neighbor_score - current_score
                probability = math.exp(delta / temperature)

                if random.random() < probability:
                    current_solution = neighbor_solution
                    current_score = neighbor_score

            iteration_scores.append(current_score)

            # Cool down
            temperature *= self.sa_config["cooling_rate"]

            if temperature < self.sa_config["min_temperature"]:
                break

            if iteration % 100 == 0:
                logger.info(f"Iteration {iteration}: Current = {current_score:.4f}, "
                          f"Best = {best_score:.4f}, Temp = {temperature:.4f}")

        assignments = await self._convert_solution_to_assignments(best_solution, requests, executors)

        return {
            "assignments": assignments,
            "score": best_score,
            "metrics": {
                "iterations": iteration,
                "final_temperature": temperature,
                "acceptance_ratio": len([s for s in iteration_scores if s > iteration_scores[0]]) / len(iteration_scores)
            },
            "details": {
                "algorithm": "simulated_annealing",
                "convergence_scores": iteration_scores[-50:]  # Last 50 iterations
            }
        }

    async def _hybrid_optimization(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Hybrid optimization combining multiple algorithms
        """
        logger.info("Starting Hybrid optimization")

        # Phase 1: Geographic clustering
        geographic_clusters = await self.geo_optimizer.cluster_requests_by_geography(requests)

        # Phase 2: Apply different algorithms to different sized clusters
        all_assignments = []
        algorithm_usage = {}

        for district, cluster_requests in geographic_clusters.items():
            cluster_size = len(cluster_requests)

            if cluster_size <= 3:
                # Small clusters: Use greedy algorithm
                algorithm = "greedy"
                cluster_result = await self._greedy_optimization(cluster_requests, executors)
            elif cluster_size <= 8:
                # Medium clusters: Use Simulated Annealing
                algorithm = "simulated_annealing"
                cluster_result = await self._simulated_annealing_optimization(cluster_requests, executors)
            else:
                # Large clusters: Use Genetic Algorithm
                algorithm = "genetic_algorithm"
                cluster_result = await self._genetic_algorithm_optimization(cluster_requests, executors)

            all_assignments.extend(cluster_result["assignments"])
            algorithm_usage[district] = {
                "algorithm": algorithm,
                "requests": cluster_size,
                "score": cluster_result["score"]
            }

        # Phase 3: Final optimization with ML predictions
        ml_optimized_assignments = []
        for assignment in all_assignments:
            try:
                # Get ML prediction for assignment quality
                ml_features = await self._extract_ml_features(assignment, requests, executors)
                ml_prediction = await self.ml_pipeline.predict_assignment_success(ml_features)

                assignment["ml_prediction"] = ml_prediction
                assignment["confidence"] = ml_prediction.get("confidence", 0.5)

                ml_optimized_assignments.append(assignment)
            except Exception as e:
                logger.warning(f"ML prediction failed for assignment: {e}")
                assignment["ml_prediction"] = None
                assignment["confidence"] = 0.5
                ml_optimized_assignments.append(assignment)

        # Calculate overall score
        total_score = sum(a.get("confidence", 0.5) for a in ml_optimized_assignments)
        average_score = total_score / len(ml_optimized_assignments) if ml_optimized_assignments else 0

        return {
            "assignments": ml_optimized_assignments,
            "score": average_score,
            "metrics": {
                "geographic_clusters": len(geographic_clusters),
                "algorithm_usage": algorithm_usage,
                "ml_enhanced": True
            },
            "details": {
                "algorithm": "hybrid",
                "phases": ["geographic_clustering", "multi_algorithm_optimization", "ml_enhancement"]
            }
        }

    async def _create_initial_population(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]],
        population_size: int
    ) -> List[List[int]]:
        """Create initial population for genetic algorithm"""
        population = []

        for _ in range(population_size):
            solution = await self._create_random_solution(requests, executors)
            population.append(solution)

        return population

    async def _create_random_solution(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> List[int]:
        """Create random assignment solution (request_index -> executor_index)"""
        solution = []
        available_executors = list(range(len(executors)))

        for _ in requests:
            if available_executors:
                executor_idx = random.choice(available_executors)
                solution.append(executor_idx)
            else:
                # All executors assigned, allow overloading
                solution.append(random.randint(0, len(executors) - 1))

        return solution

    async def _evaluate_solution_fitness(
        self,
        solution: List[int],
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> float:
        """Evaluate fitness score for a solution"""
        total_score = 0
        executor_workloads = [0] * len(executors)

        for req_idx, exec_idx in enumerate(solution):
            request = requests[req_idx]
            executor = executors[exec_idx]

            # ML success probability
            try:
                ml_features = await self._extract_ml_features_from_indices(req_idx, exec_idx, requests, executors)
                ml_pred = await self.ml_pipeline.predict_assignment_success(ml_features)
                ml_score = ml_pred.get("success_probability", 0.5)
            except:
                ml_score = 0.5

            # Geographic efficiency
            geo_score = await self._calculate_geographic_score(request, executor)

            # Workload penalty
            executor_workloads[exec_idx] += 1
            workload_penalty = min(0.3, executor_workloads[exec_idx] * 0.05)

            # Specialization match
            spec_score = 1.0 if request.get("category") in executor.get("specializations", []) else 0.3

            # Urgency factor
            urgency = request.get("urgency", 3)
            urgency_score = (6 - urgency) / 5.0  # Higher urgency = lower score if not handled well

            # Weighted combination
            assignment_score = (
                ml_score * self.weights["ml_success_probability"] +
                geo_score * self.weights["geographic_efficiency"] +
                (1 - workload_penalty) * self.weights["executor_workload"] +
                spec_score * self.weights["executor_specialization"] +
                urgency_score * self.weights["urgency_factor"]
            )

            total_score += assignment_score

        return total_score / len(requests) if requests else 0

    async def _calculate_geographic_score(self, request: Dict[str, Any], executor: Dict[str, Any]) -> float:
        """Calculate geographic efficiency score"""
        try:
            request_district = self.geo_optimizer._extract_district_from_address(
                request.get("address", "")
            )
            executor_district = executor.get("district", "Чиланзар")

            distance = self.geo_optimizer.get_district_distance(request_district, executor_district)

            # Score based on distance (closer = better)
            max_distance = 15.0  # km
            geo_score = max(0.1, 1.0 - (distance / max_distance))

            # Bonus for same district
            if request_district == executor_district:
                geo_score += 0.2

            return min(1.0, geo_score)

        except Exception:
            return 0.5  # Default score

    async def _extract_ml_features(
        self,
        assignment: Dict[str, Any],
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract ML features from assignment"""
        # Find request and executor
        request = next((r for r in requests if r.get("request_number") == assignment.get("request_id")), {})
        executor = next((e for e in executors if e.get("executor_id") == assignment.get("executor_id")), {})

        return {
            "specialization_match": assignment.get("specialization_match", False),
            "efficiency_score": executor.get("efficiency_score", 75.0),
            "urgency": request.get("urgency", 3),
            "district_match": assignment.get("same_district", False),
            "workload": executor.get("current_assignments", 3),
            "hour_of_day": datetime.now().hour,
            "day_of_week": datetime.now().weekday()
        }

    async def _extract_ml_features_from_indices(
        self,
        req_idx: int,
        exec_idx: int,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract ML features from indices"""
        request = requests[req_idx]
        executor = executors[exec_idx]

        # Check specialization match
        spec_match = request.get("category") in executor.get("specializations", [])

        # Check district match
        req_district = self.geo_optimizer._extract_district_from_address(request.get("address", ""))
        exec_district = executor.get("district", "Чиланзар")
        district_match = req_district == exec_district

        return {
            "specialization_match": spec_match,
            "efficiency_score": executor.get("efficiency_score", 75.0),
            "urgency": request.get("urgency", 3),
            "district_match": district_match,
            "workload": executor.get("current_assignments", 3),
            "hour_of_day": datetime.now().hour,
            "day_of_week": datetime.now().weekday()
        }

    async def _greedy_optimization(
        self,
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Simple greedy optimization for small clusters"""
        assignments = []

        for request in requests:
            best_executor = None
            best_score = -1

            for executor in executors:
                if not executor.get("is_available", True):
                    continue

                # Simple scoring
                score = 0
                if request.get("category") in executor.get("specializations", []):
                    score += 0.5
                score += executor.get("efficiency_score", 75) / 100.0 * 0.3
                score += random.random() * 0.2  # Add some randomness

                if score > best_score:
                    best_score = score
                    best_executor = executor

            if best_executor:
                assignment = {
                    "request_id": request.get("request_number"),
                    "executor_id": best_executor["executor_id"],
                    "algorithm": "greedy",
                    "score": best_score
                }
                assignments.append(assignment)

        return {
            "assignments": assignments,
            "score": sum(a["score"] for a in assignments) / len(assignments) if assignments else 0
        }

    async def _tournament_selection(self, population: List, fitness_scores: List[float]) -> List:
        """Tournament selection for genetic algorithm"""
        selected = []
        tournament_size = 3

        for _ in range(len(population)):
            tournament_indices = random.sample(range(len(population)), tournament_size)
            winner_idx = max(tournament_indices, key=lambda x: fitness_scores[x])
            selected.append(copy.deepcopy(population[winner_idx]))

        return selected

    async def _crossover(self, parent1: List[int], parent2: List[int], requests: List, executors: List) -> Tuple[List[int], List[int]]:
        """Single-point crossover"""
        if len(parent1) <= 1:
            return copy.deepcopy(parent1), copy.deepcopy(parent2)

        crossover_point = random.randint(1, len(parent1) - 1)

        child1 = parent1[:crossover_point] + parent2[crossover_point:]
        child2 = parent2[:crossover_point] + parent1[crossover_point:]

        return child1, child2

    async def _mutate(self, individual: List[int], requests: List, executors: List) -> None:
        """Random mutation"""
        if not individual:
            return

        mutation_point = random.randint(0, len(individual) - 1)
        individual[mutation_point] = random.randint(0, len(executors) - 1)

    async def _generate_neighbor_solution(self, solution: List[int], requests: List, executors: List) -> List[int]:
        """Generate neighbor solution for simulated annealing"""
        neighbor = copy.deepcopy(solution)

        if len(neighbor) >= 2:
            # Swap two random assignments
            idx1, idx2 = random.sample(range(len(neighbor)), 2)
            neighbor[idx1], neighbor[idx2] = neighbor[idx2], neighbor[idx1]

        return neighbor

    async def _convert_solution_to_assignments(
        self,
        solution: List[int],
        requests: List[Dict[str, Any]],
        executors: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert solution array to assignment list"""
        assignments = []

        for req_idx, exec_idx in enumerate(solution):
            request = requests[req_idx]
            executor = executors[exec_idx]

            assignment = {
                "request_id": request.get("request_number"),
                "executor_id": executor["executor_id"],
                "algorithm": "advanced_optimization",
                "request_category": request.get("category"),
                "executor_specializations": executor.get("specializations", []),
                "specialization_match": request.get("category") in executor.get("specializations", [])
            }

            assignments.append(assignment)

        return assignments

    async def health_check(self) -> str:
        """Health check for Advanced Optimizer"""
        try:
            # Test basic optimization
            test_requests = [{"request_number": "test-001", "category": "general", "urgency": 3, "address": "Чиланзар"}]
            test_executors = [{"executor_id": 1, "specializations": ["general"], "efficiency_score": 85, "district": "Чиланзар", "is_available": True}]

            result = await self._greedy_optimization(test_requests, test_executors)

            if not result.get("assignments"):
                return "unhealthy: optimization failed"

            return "healthy"

        except Exception as e:
            logger.error(f"Advanced Optimizer health check failed: {e}")
            return f"unhealthy: {str(e)}"
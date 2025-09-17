"""
GeoOptimizer - Геооптимизатор для оптимизации маршрутов исполнителей
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass, field
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
import math
import statistics
import json
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.constants import REQUEST_STATUSES, SHIFT_STATUSES

logger = logging.getLogger(__name__)


@dataclass
class GeoPoint:
    """Географическая точка"""
    latitude: float
    longitude: float
    address: str = ""
    
    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Недопустимая широта: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Недопустимая долгота: {self.longitude}")


@dataclass
class RoutePoint:
    """Точка маршрута с дополнительной информацией"""
    geo_point: GeoPoint
    request_number: str
    priority: str
    estimated_duration: int  # в минутах
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None


@dataclass
class RouteOptimizationResult:
    """Результат оптимизации маршрута"""
    executor_id: int
    original_points: List[RoutePoint]
    optimized_points: List[RoutePoint]
    total_distance_km: float
    estimated_travel_time: int  # в минутах
    fuel_savings_percent: float
    time_savings_minutes: int
    optimization_algorithm: str
    route_efficiency_score: float
    improvements: List[str] = field(default_factory=list)


class GeoOptimizer:
    """Геооптимизатор для планирования оптимальных маршрутов исполнителей"""
    
    def __init__(self, db: Session):
        self.db = db
        self.earth_radius_km = 6371.0
        self.average_speed_kmh = 40.0  # средняя скорость в городе
        self.fuel_consumption_l_per_km = 0.08  # средний расход топлива
        
        # Параметры оптимизации
        self.max_route_points = 12  # максимум точек в одном маршруте
        self.max_route_duration_hours = 8  # максимум часов в маршруте
        self.priority_weights = {
            'urgent': 3.0,
            'high': 2.0,
            'medium': 1.5,
            'low': 1.0
        }
    
    def optimize_daily_routes(self, date: datetime, executor_ids: Optional[List[int]] = None) -> List[RouteOptimizationResult]:
        """Оптимизирует маршруты исполнителей на день"""
        try:
            logger.info(f"Начинаю оптимизацию маршрутов на {date.date()}")
            
            # Получаем смены на указанную дату
            shifts = self._get_shifts_for_date(date, executor_ids)
            if not shifts:
                logger.warning(f"Нет смен на {date.date()}")
                return []
            
            results = []
            
            for shift in shifts:
                # Получаем заявки для смены
                assignments = self._get_shift_assignments(shift.id)
                if not assignments:
                    continue
                
                # Преобразуем в точки маршрута
                route_points = self._assignments_to_route_points(assignments)
                if len(route_points) < 2:
                    continue  # Недостаточно точек для оптимизации
                
                # Оптимизируем маршрут
                result = self._optimize_route_for_executor(shift.user_id, route_points)
                if result:
                    results.append(result)
            
            logger.info(f"Оптимизировано {len(results)} маршрутов")
            return results
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации маршрутов: {e}")
            return []
    
    def optimize_executor_route(self, executor_id: int, request_ids: List[int]) -> Optional[RouteOptimizationResult]:
        """Оптимизирует маршрут для конкретного исполнителя"""
        try:
            # Получаем заявки
            requests = self.db.query(Request).filter(
                Request.id.in_(request_ids)
            ).all()
            
            if not requests:
                logger.warning(f"Не найдены заявки для оптимизации маршрута исполнителя {executor_id}")
                return None
            
            # Преобразуем в точки маршрута
            route_points = []
            for request in requests:
                geo_point = self._extract_geo_point_from_request(request)
                if geo_point:
                    route_points.append(RoutePoint(
                        geo_point=geo_point,
                        request_number=request.request_number,
                        priority=request.priority or 'medium',
                        estimated_duration=request.estimated_duration or 60
                    ))
            
            if len(route_points) < 2:
                logger.warning(f"Недостаточно географических точек для оптимизации")
                return None
            
            return self._optimize_route_for_executor(executor_id, route_points)
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации маршрута исполнителя {executor_id}: {e}")
            return None
    
    def calculate_route_metrics(self, route_points: List[RoutePoint]) -> Dict[str, Any]:
        """Вычисляет метрики маршрута"""
        try:
            if len(route_points) < 2:
                return {}
            
            total_distance = 0.0
            total_duration = 0
            
            # Вычисляем общее расстояние
            for i in range(len(route_points) - 1):
                distance = self._calculate_distance(
                    route_points[i].geo_point,
                    route_points[i + 1].geo_point
                )
                total_distance += distance
            
            # Вычисляем время в пути
            travel_time = total_distance / self.average_speed_kmh * 60  # в минутах
            
            # Добавляем время на выполнение работ
            work_time = sum(point.estimated_duration for point in route_points)
            total_duration = int(travel_time + work_time)
            
            # Вычисляем расход топлива
            fuel_consumption = total_distance * self.fuel_consumption_l_per_km
            
            return {
                'total_distance_km': round(total_distance, 2),
                'travel_time_minutes': int(travel_time),
                'work_time_minutes': work_time,
                'total_duration_minutes': total_duration,
                'fuel_consumption_liters': round(fuel_consumption, 2),
                'number_of_points': len(route_points),
                'efficiency_score': self._calculate_route_efficiency(route_points)
            }
            
        except Exception as e:
            logger.error(f"Ошибка вычисления метрик маршрута: {e}")
            return {}
    
    def suggest_route_optimizations(self, route_points: List[RoutePoint]) -> List[str]:
        """Предлагает улучшения для маршрута"""
        try:
            suggestions = []
            
            if len(route_points) < 2:
                return suggestions
            
            # Анализируем эффективность маршрута
            metrics = self.calculate_route_metrics(route_points)
            
            # Проверяем длину маршрута
            if metrics.get('total_distance_km', 0) > 100:
                suggestions.append("Маршрут слишком длинный, рассмотрите разбивку на несколько дней")
            
            # Проверяем время выполнения
            if metrics.get('total_duration_minutes', 0) > self.max_route_duration_hours * 60:
                suggestions.append("Превышено максимальное время маршрута, нужно сократить количество заявок")
            
            # Проверяем количество точек
            if len(route_points) > self.max_route_points:
                suggestions.append(f"Слишком много точек в маршруте ({len(route_points)}), оптимально до {self.max_route_points}")
            
            # Проверяем эффективность
            efficiency = metrics.get('efficiency_score', 0)
            if efficiency < 0.6:
                suggestions.append("Низкая эффективность маршрута, рассмотрите перестановку точек")
            elif efficiency > 0.8:
                suggestions.append("Маршрут уже хорошо оптимизирован")
            
            # Проверяем приоритеты
            urgent_points = [p for p in route_points if p.priority == 'urgent']
            if urgent_points and route_points.index(urgent_points[0]) > 2:
                suggestions.append("Срочные заявки лучше выполнять в начале дня")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Ошибка анализа маршрута: {e}")
            return []
    
    def find_nearby_requests(self, center_point: GeoPoint, radius_km: float, 
                           exclude_request_ids: Optional[Set[int]] = None) -> List[Request]:
        """Находит заявки в радиусе от заданной точки"""
        try:
            exclude_ids = exclude_request_ids or set()
            
            # Получаем все активные заявки
            requests = self.db.query(Request).filter(
                and_(
                    Request.status.in_(['new', 'in_progress']),
                    ~Request.id.in_(exclude_ids)
                )
            ).all()
            
            nearby_requests = []
            
            for request in requests:
                request_point = self._extract_geo_point_from_request(request)
                if request_point:
                    distance = self._calculate_distance(center_point, request_point)
                    if distance <= radius_km:
                        nearby_requests.append(request)
            
            # Сортируем по расстоянию
            nearby_requests.sort(key=lambda r: self._calculate_distance(
                center_point, self._extract_geo_point_from_request(r)
            ))
            
            return nearby_requests
            
        except Exception as e:
            logger.error(f"Ошибка поиска близких заявок: {e}")
            return []
    
    def cluster_requests_by_location(self, requests: List[Request], max_clusters: int = 5) -> List[List[Request]]:
        """Группирует заявки по географическому расположению"""
        try:
            if not requests:
                return []
            
            # Извлекаем географические точки
            points_with_requests = []
            for request in requests:
                geo_point = self._extract_geo_point_from_request(request)
                if geo_point:
                    points_with_requests.append((geo_point, request))
            
            if not points_with_requests:
                return []
            
            # Простая кластеризация на основе расстояния
            clusters = []
            used_indices = set()
            
            for i, (point, request) in enumerate(points_with_requests):
                if i in used_indices:
                    continue
                
                cluster = [request]
                used_indices.add(i)
                
                # Ищем близкие точки
                for j, (other_point, other_request) in enumerate(points_with_requests):
                    if j in used_indices:
                        continue
                    
                    distance = self._calculate_distance(point, other_point)
                    if distance <= 5.0:  # радиус кластера 5 км
                        cluster.append(other_request)
                        used_indices.add(j)
                
                clusters.append(cluster)
                
                if len(clusters) >= max_clusters:
                    break
            
            # Сортируем кластеры по размеру (больше сначала)
            clusters.sort(key=len, reverse=True)
            
            return clusters
            
        except Exception as e:
            logger.error(f"Ошибка кластеризации заявок: {e}")
            return []
    
    # Приватные методы
    
    def _optimize_route_for_executor(self, executor_id: int, route_points: List[RoutePoint]) -> Optional[RouteOptimizationResult]:
        """Оптимизирует маршрут для конкретного исполнителя"""
        try:
            original_points = route_points.copy()
            
            # Вычисляем метрики до оптимизации
            original_metrics = self.calculate_route_metrics(original_points)
            
            # Применяем различные алгоритмы оптимизации
            optimized_points = self._apply_route_optimization(route_points)
            
            # Вычисляем метрики после оптимизации
            optimized_metrics = self.calculate_route_metrics(optimized_points)
            
            # Вычисляем улучшения
            distance_savings = original_metrics.get('total_distance_km', 0) - optimized_metrics.get('total_distance_km', 0)
            time_savings = original_metrics.get('total_duration_minutes', 0) - optimized_metrics.get('total_duration_minutes', 0)
            fuel_savings = (distance_savings / original_metrics.get('total_distance_km', 1)) * 100
            
            improvements = self.suggest_route_optimizations(optimized_points)
            
            return RouteOptimizationResult(
                executor_id=executor_id,
                original_points=original_points,
                optimized_points=optimized_points,
                total_distance_km=optimized_metrics.get('total_distance_km', 0),
                estimated_travel_time=optimized_metrics.get('travel_time_minutes', 0),
                fuel_savings_percent=max(0, fuel_savings),
                time_savings_minutes=max(0, time_savings),
                optimization_algorithm="priority_nearest_neighbor",
                route_efficiency_score=optimized_metrics.get('efficiency_score', 0),
                improvements=improvements
            )
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации маршрута для исполнителя {executor_id}: {e}")
            return None
    
    def _apply_route_optimization(self, route_points: List[RoutePoint]) -> List[RoutePoint]:
        """Применяет алгоритм оптимизации маршрута"""
        try:
            if len(route_points) <= 2:
                return route_points
            
            # Сортируем по приоритету и времени
            optimized = route_points.copy()
            
            # 1. Срочные заявки вперед
            urgent_points = [p for p in optimized if p.priority == 'urgent']
            other_points = [p for p in optimized if p.priority != 'urgent']
            
            # 2. Оптимизируем обычные заявки по расстоянию (жадный алгоритм)
            if len(other_points) > 1:
                other_optimized = self._nearest_neighbor_optimization(other_points)
            else:
                other_optimized = other_points
            
            # 3. Объединяем результаты
            final_route = urgent_points + other_optimized
            
            return final_route
            
        except Exception as e:
            logger.error(f"Ошибка применения оптимизации маршрута: {e}")
            return route_points
    
    def _nearest_neighbor_optimization(self, points: List[RoutePoint]) -> List[RoutePoint]:
        """Алгоритм ближайшего соседа для оптимизации маршрута"""
        try:
            if len(points) <= 1:
                return points
            
            optimized = []
            remaining = points.copy()
            
            # Начинаем с первой точки
            current = remaining.pop(0)
            optimized.append(current)
            
            # Жадно выбираем ближайшую точку
            while remaining:
                current_point = current.geo_point
                
                # Находим ближайшую точку
                nearest_idx = 0
                min_distance = self._calculate_distance(current_point, remaining[0].geo_point)
                
                for i in range(1, len(remaining)):
                    distance = self._calculate_distance(current_point, remaining[i].geo_point)
                    if distance < min_distance:
                        min_distance = distance
                        nearest_idx = i
                
                current = remaining.pop(nearest_idx)
                optimized.append(current)
            
            return optimized
            
        except Exception as e:
            logger.error(f"Ошибка алгоритма ближайшего соседа: {e}")
            return points
    
    def _calculate_distance(self, point1: GeoPoint, point2: GeoPoint) -> float:
        """Вычисляет расстояние между двумя географическими точками в км"""
        try:
            # Формула гаверсинуса
            lat1_rad = math.radians(point1.latitude)
            lon1_rad = math.radians(point1.longitude)
            lat2_rad = math.radians(point2.latitude)
            lon2_rad = math.radians(point2.longitude)
            
            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad
            
            a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            
            distance = self.earth_radius_km * c
            
            return distance
            
        except Exception as e:
            logger.error(f"Ошибка вычисления расстояния: {e}")
            return 0.0
    
    def _calculate_route_efficiency(self, route_points: List[RoutePoint]) -> float:
        """Вычисляет коэффициент эффективности маршрута"""
        try:
            if len(route_points) < 2:
                return 0.0
            
            # Вычисляем фактическое расстояние
            actual_distance = 0.0
            for i in range(len(route_points) - 1):
                actual_distance += self._calculate_distance(
                    route_points[i].geo_point,
                    route_points[i + 1].geo_point
                )
            
            # Вычисляем теоретически минимальное расстояние (прямая линия)
            if len(route_points) == 2:
                min_distance = self._calculate_distance(
                    route_points[0].geo_point,
                    route_points[-1].geo_point
                )
            else:
                # Упрощенная оценка через центр масс
                center_lat = sum(p.geo_point.latitude for p in route_points) / len(route_points)
                center_lon = sum(p.geo_point.longitude for p in route_points) / len(route_points)
                center_point = GeoPoint(center_lat, center_lon)
                
                min_distance = sum(
                    self._calculate_distance(center_point, p.geo_point) 
                    for p in route_points
                ) * 2 / len(route_points)
            
            # Коэффициент эффективности
            if actual_distance == 0:
                return 1.0
            
            efficiency = min_distance / actual_distance
            return min(1.0, efficiency)
            
        except Exception as e:
            logger.error(f"Ошибка вычисления эффективности маршрута: {e}")
            return 0.0
    
    def _get_shifts_for_date(self, date: datetime, executor_ids: Optional[List[int]] = None) -> List[Shift]:
        """Получает смены на указанную дату"""
        try:
            query = self.db.query(Shift).filter(
                and_(
                    Shift.date == date.date(),
                    Shift.status.in_(['active', 'planned'])
                )
            )
            
            if executor_ids:
                query = query.filter(Shift.user_id.in_(executor_ids))
            
            return query.all()
            
        except Exception as e:
            logger.error(f"Ошибка получения смен на {date.date()}: {e}")
            return []
    
    def _get_shift_assignments(self, shift_id: int) -> List[ShiftAssignment]:
        """Получает назначения для смены"""
        try:
            return self.db.query(ShiftAssignment).filter(
                and_(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.status == 'active'
                )
            ).all()
            
        except Exception as e:
            logger.error(f"Ошибка получения назначений для смены {shift_id}: {e}")
            return []
    
    def _assignments_to_route_points(self, assignments: List[ShiftAssignment]) -> List[RoutePoint]:
        """Преобразует назначения в точки маршрута"""
        try:
            route_points = []
            
            for assignment in assignments:
                request = self.db.query(Request).filter(Request.id == assignment.request_id).first()
                if not request:
                    continue
                
                geo_point = self._extract_geo_point_from_request(request)
                if geo_point:
                    route_points.append(RoutePoint(
                        geo_point=geo_point,
                        request_number=request.request_number,
                        priority=request.priority or 'medium',
                        estimated_duration=request.estimated_duration or 60
                    ))
            
            return route_points
            
        except Exception as e:
            logger.error(f"Ошибка преобразования назначений в точки маршрута: {e}")
            return []
    
    def _extract_geo_point_from_request(self, request: Request) -> Optional[GeoPoint]:
        """Извлекает географическую точку из заявки"""
        try:
            # Пытаемся извлечь координаты из дополнительных данных
            if hasattr(request, 'additional_data') and request.additional_data:
                if isinstance(request.additional_data, str):
                    import json
                    data = json.loads(request.additional_data)
                else:
                    data = request.additional_data
                
                if 'latitude' in data and 'longitude' in data:
                    return GeoPoint(
                        latitude=float(data['latitude']),
                        longitude=float(data['longitude']),
                        address=data.get('address', request.address or '')
                    )
            
            # Если координат нет, пытаемся геокодировать адрес
            if request.address:
                # Упрощенная геокодировка для демонстрации
                # В реальности здесь должен быть вызов API геокодирования
                geo_point = self._simple_geocode(request.address)
                if geo_point:
                    return geo_point
            
            # Используем координаты по умолчанию (центр города)
            logger.warning(f"Не удалось определить координаты для заявки {request.request_number}")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка извлечения географической точки из заявки {request.request_number}: {e}")
            return None
    
    def _simple_geocode(self, address: str) -> Optional[GeoPoint]:
        """Упрощенная геокодировка адреса"""
        try:
            # Это заглушка для демонстрации
            # В реальности здесь должен быть вызов геокодирующего сервиса
            
            # Примерные координаты для разных районов города
            district_coords = {
                'центр': (55.7558, 37.6176),
                'север': (55.8558, 37.6176),
                'юг': (55.6558, 37.6176),
                'восток': (55.7558, 37.7176),
                'запад': (55.7558, 37.5176)
            }
            
            address_lower = address.lower()
            for district, (lat, lon) in district_coords.items():
                if district in address_lower:
                    return GeoPoint(
                        latitude=lat + (hash(address) % 100) / 10000.0,  # небольшое случайное смещение
                        longitude=lon + (hash(address) % 100) / 10000.0,
                        address=address
                    )
            
            # Координаты по умолчанию (центр Москвы)
            return GeoPoint(
                latitude=55.7558 + (hash(address) % 100) / 5000.0,
                longitude=37.6176 + (hash(address) % 100) / 5000.0,
                address=address
            )
            
        except Exception as e:
            logger.error(f"Ошибка геокодировки адреса '{address}': {e}")
            return None
#!/usr/bin/env python3
"""
Интеграционный тест аналитических компонентов системы смен
Тестирует работу ShiftAnalytics, MetricsManager и RecommendationEngine
"""

import asyncio
import sys
import os
from datetime import datetime, date, timedelta
from typing import Dict, Any

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from uk_management_bot.database.session import get_db
from uk_management_bot.services.shift_analytics import ShiftAnalytics
from uk_management_bot.services.metrics_manager import MetricsManager
from uk_management_bot.services.recommendation_engine import RecommendationEngine
from uk_management_bot.services.shift_planning_service import ShiftPlanningService


class AnalyticsIntegrationTest:
    """Класс для интеграционного тестирования аналитики"""
    
    def __init__(self):
        self.db = None
        self.analytics = None
        self.metrics = None
        self.recommendation_engine = None
        self.planning_service = None
    
    async def setup(self):
        """Инициализация компонентов для тестирования"""
        try:
            print("🔧 Инициализация тестовой среды...")
            
            # Подключение к БД
            self.db = next(get_db())
            print("✅ Подключение к БД установлено")
            
            # Инициализация сервисов
            self.analytics = ShiftAnalytics(self.db)
            self.metrics = MetricsManager(self.db)
            self.recommendation_engine = RecommendationEngine(self.db)
            self.planning_service = ShiftPlanningService(self.db)
            
            print("✅ Аналитические сервисы инициализированы")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка инициализации: {e}")
            return False
    
    async def test_shift_analytics(self) -> Dict[str, Any]:
        """Тест ShiftAnalytics"""
        print("\n📊 Тестирование ShiftAnalytics...")
        results = {}
        
        try:
            # Тест 1: Расчет эффективности смен
            print("  • Тестирование расчета эффективности смен")
            
            # Получаем несколько смен для тестирования
            from uk_management_bot.database.models.shift import Shift
            shifts = self.db.query(Shift).limit(5).all()
            
            if shifts:
                shift_scores = []
                for shift in shifts[:3]:  # Тестируем на 3 сменах
                    try:
                        score = await self.analytics.calculate_shift_efficiency_score(shift.id)
                        if score:
                            shift_scores.append(score)
                            print(f"    ✓ Смена {shift.id}: оценка {score.get('overall_score', 'N/A')}")
                    except Exception as e:
                        print(f"    ⚠️ Ошибка расчета для смены {shift.id}: {e}")
                
                results['shift_efficiency_tests'] = len(shift_scores)
                results['average_score'] = sum(s.get('overall_score', 0) for s in shift_scores) / len(shift_scores) if shift_scores else 0
            else:
                print("    ⚠️ Нет смен для тестирования")
                results['shift_efficiency_tests'] = 0
            
            # Тест 2: Анализ трендов
            print("  • Тестирование анализа трендов")
            try:
                trends = await self.analytics.get_performance_trends(
                    start_date=date.today() - timedelta(days=30),
                    end_date=date.today()
                )
                results['trends_analysis'] = 'success' if trends else 'no_data'
                print(f"    ✓ Анализ трендов: {len(trends.get('daily_trends', []))} дней")
            except Exception as e:
                results['trends_analysis'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка анализа трендов: {e}")
            
            # Тест 3: Расчет KPI
            print("  • Тестирование расчета KPI")
            try:
                kpis = await self.analytics.calculate_kpis(
                    start_date=date.today() - timedelta(days=7),
                    end_date=date.today()
                )
                results['kpi_calculation'] = 'success' if kpis else 'no_data'
                print(f"    ✓ KPI рассчитаны: {len(kpis.get('kpis', {}))} показателей")
            except Exception as e:
                results['kpi_calculation'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка расчета KPI: {e}")
            
            return results
            
        except Exception as e:
            print(f"❌ Критическая ошибка в тестировании ShiftAnalytics: {e}")
            return {'error': str(e)}
    
    async def test_metrics_manager(self) -> Dict[str, Any]:
        """Тест MetricsManager"""
        print("\n📈 Тестирование MetricsManager...")
        results = {}
        
        try:
            # Тест 1: Расчет периодных метрик
            print("  • Тестирование расчета периодных метрик")
            try:
                period_metrics = await self.metrics.calculate_period_metrics(
                    start_date=date.today() - timedelta(days=7),
                    end_date=date.today()
                )
                results['period_metrics'] = 'success' if period_metrics else 'no_data'
                print(f"    ✓ Периодные метрики: {len(period_metrics.get('metrics', {}))} показателей")
            except Exception as e:
                results['period_metrics'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка расчета периодных метрик: {e}")
            
            # Тест 2: Дашборд метрик
            print("  • Тестирование дашборда метрик")
            try:
                dashboard = await self.metrics.get_metrics_dashboard()
                results['dashboard'] = 'success' if dashboard else 'no_data'
                print(f"    ✓ Дашборд сгенерирован: {len(dashboard.get('sections', []))} секций")
            except Exception as e:
                results['dashboard'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка генерации дашборда: {e}")
            
            # Тест 3: Исторические метрики
            print("  • Тестирование исторических метрик")
            try:
                historical = await self.metrics.get_historical_metrics(
                    metric_names=['efficiency_score', 'completion_rate'],
                    days_back=14
                )
                results['historical_metrics'] = 'success' if historical else 'no_data'
                print(f"    ✓ Исторические метрики: {len(historical.get('metrics', {}))} показателей")
            except Exception as e:
                results['historical_metrics'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка получения исторических метрик: {e}")
            
            return results
            
        except Exception as e:
            print(f"❌ Критическая ошибка в тестировании MetricsManager: {e}")
            return {'error': str(e)}
    
    async def test_recommendation_engine(self) -> Dict[str, Any]:
        """Тест RecommendationEngine"""
        print("\n🤖 Тестирование RecommendationEngine...")
        results = {}
        
        try:
            # Тест 1: Генерация комплексных рекомендаций
            print("  • Тестирование комплексных рекомендаций")
            try:
                recommendations = await self.recommendation_engine.generate_comprehensive_recommendations(
                    period_days=7
                )
                results['comprehensive_recommendations'] = 'success' if recommendations else 'no_data'
                print(f"    ✓ Комплексные рекомендации: {len(recommendations.get('recommendations', []))} элементов")
            except Exception as e:
                results['comprehensive_recommendations'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка генерации комплексных рекомендаций: {e}")
            
            # Тест 2: Рекомендации по оптимизации смен
            print("  • Тестирование рекомендаций по оптимизации смен")
            try:
                shift_recommendations = await self.recommendation_engine.get_shift_optimization_recommendations(
                    target_date=date.today()
                )
                results['shift_optimization'] = 'success' if shift_recommendations else 'no_data'
                print(f"    ✓ Рекомендации по оптимизации: {len(shift_recommendations.get('recommendations', []))} рекомендаций")
            except Exception as e:
                results['shift_optimization'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка рекомендаций по оптимизации: {e}")
            
            # Тест 3: Прогнозы производительности
            print("  • Тестирование прогнозов производительности")
            try:
                performance_forecast = await self.recommendation_engine.predict_performance_trends(
                    days_ahead=7
                )
                results['performance_forecast'] = 'success' if performance_forecast else 'no_data'
                print(f"    ✓ Прогноз производительности: {len(performance_forecast.get('predictions', []))} дней")
            except Exception as e:
                results['performance_forecast'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка прогноза производительности: {e}")
            
            return results
            
        except Exception as e:
            print(f"❌ Критическая ошибка в тестировании RecommendationEngine: {e}")
            return {'error': str(e)}
    
    async def test_planning_service_integration(self) -> Dict[str, Any]:
        """Тест интеграции аналитики в ShiftPlanningService"""
        print("\n🔗 Тестирование интеграции с ShiftPlanningService...")
        results = {}
        
        try:
            # Тест 1: Комплексная аналитика
            print("  • Тестирование комплексной аналитики")
            try:
                analytics = await self.planning_service.get_comprehensive_analytics(
                    start_date=date.today() - timedelta(days=7),
                    end_date=date.today(),
                    include_recommendations=True
                )
                results['comprehensive_analytics'] = 'success' if analytics else 'no_data'
                print(f"    ✓ Комплексная аналитика: {len(analytics.get('recommendations', []))} рекомендаций")
            except Exception as e:
                results['comprehensive_analytics'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка комплексной аналитики: {e}")
            
            # Тест 2: Рекомендации по оптимизации
            print("  • Тестирование рекомендаций по оптимизации")
            try:
                optimization = await self.planning_service.get_optimization_recommendations(
                    target_date=date.today()
                )
                results['optimization_recommendations'] = 'success' if optimization else 'no_data'
                print(f"    ✓ Рекомендации по оптимизации: {len(optimization.get('optimization_suggestions', []))} предложений")
            except Exception as e:
                results['optimization_recommendations'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка рекомендаций по оптимизации: {e}")
            
            # Тест 3: Прогнозирование рабочей нагрузки
            print("  • Тестирование прогнозирования рабочей нагрузки")
            try:
                workload_prediction = await self.planning_service.predict_workload(
                    target_date=date.today() + timedelta(days=1),
                    days_ahead=5
                )
                results['workload_prediction'] = 'success' if workload_prediction else 'no_data'
                print(f"    ✓ Прогноз рабочей нагрузки: {len(workload_prediction.get('daily_predictions', []))} дней")
            except Exception as e:
                results['workload_prediction'] = f'error: {str(e)}'
                print(f"    ❌ Ошибка прогнозирования нагрузки: {e}")
            
            return results
            
        except Exception as e:
            print(f"❌ Критическая ошибка в тестировании интеграции: {e}")
            return {'error': str(e)}
    
    async def run_full_test(self) -> Dict[str, Any]:
        """Запуск полного цикла тестирования"""
        print("🚀 Запуск полного интеграционного тестирования аналитических компонентов")
        print("=" * 80)
        
        # Инициализация
        if not await self.setup():
            return {'error': 'Ошибка инициализации'}
        
        # Выполняем тесты
        results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        try:
            # Тест 1: ShiftAnalytics
            results['tests']['shift_analytics'] = await self.test_shift_analytics()
            
            # Тест 2: MetricsManager
            results['tests']['metrics_manager'] = await self.test_metrics_manager()
            
            # Тест 3: RecommendationEngine
            results['tests']['recommendation_engine'] = await self.test_recommendation_engine()
            
            # Тест 4: Интеграция с ShiftPlanningService
            results['tests']['planning_service_integration'] = await self.test_planning_service_integration()
            
            # Сводка результатов
            print("\n" + "=" * 80)
            print("📋 СВОДКА РЕЗУЛЬТАТОВ ТЕСТИРОВАНИЯ")
            print("=" * 80)
            
            total_tests = 0
            successful_tests = 0
            
            for service, test_results in results['tests'].items():
                print(f"\n🔧 {service.upper()}:")
                for test_name, test_result in test_results.items():
                    total_tests += 1
                    if test_result == 'success':
                        successful_tests += 1
                        status = "✅ УСПЕХ"
                    elif 'error:' in str(test_result):
                        status = "❌ ОШИБКА"
                    else:
                        status = "⚠️  ПРЕДУПРЕЖДЕНИЕ"
                    
                    print(f"  • {test_name}: {status}")
                    if 'error:' in str(test_result):
                        print(f"    {test_result}")
            
            success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
            
            print(f"\n🎯 ИТОГОВАЯ СТАТИСТИКА:")
            print(f"  • Всего тестов: {total_tests}")
            print(f"  • Успешных: {successful_tests}")
            print(f"  • Процент успеха: {success_rate:.1f}%")
            
            if success_rate >= 80:
                print("  🎉 Аналитические компоненты работают отлично!")
            elif success_rate >= 60:
                print("  👍 Аналитические компоненты работают удовлетворительно")
            else:
                print("  ⚠️  Аналитические компоненты требуют доработки")
            
            results['summary'] = {
                'total_tests': total_tests,
                'successful_tests': successful_tests,
                'success_rate': success_rate,
                'status': 'excellent' if success_rate >= 80 else 'good' if success_rate >= 60 else 'needs_work'
            }
            
            return results
            
        except Exception as e:
            print(f"❌ Критическая ошибка во время тестирования: {e}")
            results['critical_error'] = str(e)
            return results
        
        finally:
            if self.db:
                self.db.close()
                print("\n🔌 Соединение с БД закрыто")


async def main():
    """Главная функция для запуска тестов"""
    test_runner = AnalyticsIntegrationTest()
    results = await test_runner.run_full_test()
    
    # Возвращаем код выхода в зависимости от результатов
    if 'critical_error' in results:
        sys.exit(1)
    elif results.get('summary', {}).get('success_rate', 0) < 50:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
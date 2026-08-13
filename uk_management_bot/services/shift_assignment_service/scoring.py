from datetime import timedelta
from typing import List, Dict
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from uk_management_bot.utils.business_time import (
    business_date_of,
    business_days_window,
)

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
import logging

from ._types import ExecutorScore

logger = logging.getLogger(__name__)


class ScoringEngine:
    """Скоринг соответствия исполнителя смене (извлечено из ShiftAssignmentService, ARC-03).
    Read-only: использует self.db и self.weights, без побочных эффектов."""

    def __init__(self, db: Session, weights: Dict[str, float]):
        self.db = db
        self.weights = weights

    def _evaluate_executors_for_shift(
        self,
        shift: Shift,
        executors: List[User]
    ) -> List[ExecutorScore]:
        """Оценивает исполнителей для назначения на смену"""
        scores = []

        for executor in executors:
            try:
                score = self._calculate_executor_score(shift, executor)
                if score.total_score > 0:  # Только подходящих исполнителей
                    scores.append(score)
            except Exception as e:
                logger.error(f"Ошибка оценки исполнителя {executor.id}: {e}")

        return scores

    def _calculate_executor_score(self, shift: Shift, executor: User) -> ExecutorScore:
        """Рассчитывает оценку исполнителя для назначения на смену"""

        # 1. Соответствие специализации (КРИТИЧЕСКАЯ ПРОВЕРКА)
        specialization_score = self._calculate_specialization_match(shift, executor)

        # БЛОКИРОВКА: Если специализация не подходит - исполнитель не рассматривается
        if specialization_score < 0:
            return ExecutorScore(
                executor_id=executor.id,
                executor_name=f"{executor.first_name} {executor.last_name}",
                total_score=-1.0,  # Блокирующая оценка
                specialization_match=specialization_score,
                workload_score=0.0,
                rating_score=0.0,
                availability_score=0.0,
                preference_score=0.0,
                geographic_score=0.0,
                conflict_penalties=0.0,
                reasons=["❌ Нет требуемых специализаций для смены"]
            )

        # 2. Оценка загруженности
        workload_score = self._calculate_workload_score(shift, executor)

        # 3. Рейтинг исполнителя
        rating_score = self._calculate_rating_score(executor)

        # 4. Доступность
        availability_score = self._calculate_availability_score(shift, executor)

        # 5. Предпочтения исполнителя
        preference_score = self._calculate_preference_score(shift, executor)

        # 6. Географическая близость
        geographic_score = self._calculate_geographic_score(shift, executor)

        # 7. Штрафы за конфликты
        conflict_penalties = self._calculate_conflict_penalties(shift, executor)

        # Общая оценка
        total_score = (
            specialization_score * self.weights['specialization'] +
            workload_score * self.weights['workload'] +
            rating_score * self.weights['rating'] +
            availability_score * self.weights['availability'] +
            preference_score * self.weights['preference'] +
            geographic_score * self.weights['geographic'] -
            conflict_penalties
        )

        # Собираем причины оценки
        reasons = []
        if specialization_score > 0.8:
            reasons.append("✅ Отличное соответствие специализации")
        elif specialization_score > 0.5:
            reasons.append("✓ Подходящая специализация")
        if workload_score > 0.7:
            reasons.append("✓ Низкая текущая нагрузка")
        if rating_score > 0.8:
            reasons.append("⭐ Высокий рейтинг исполнителя")
        if availability_score == 1.0:
            reasons.append("✓ Полная доступность")
        if conflict_penalties > 0:
            reasons.append("⚠️ Есть незначительные конфликты")

        return ExecutorScore(
            executor_id=executor.id,
            executor_name=f"{executor.first_name} {executor.last_name}",
            total_score=max(0, total_score),  # Не может быть отрицательной
            specialization_match=specialization_score,
            workload_score=workload_score,
            rating_score=rating_score,
            availability_score=availability_score,
            preference_score=preference_score,
            geographic_score=geographic_score,
            conflict_penalties=conflict_penalties,
            reasons=reasons
        )

    # ========== МЕТОДЫ РАСЧЕТА ОЦЕНОК ==========

    def _calculate_specialization_match(self, shift: Shift, executor: User) -> float:
        """Рассчитывает соответствие специализации исполнителя требованиям смены

        КРИТИЧЕСКАЯ ПРОВЕРКА: Исполнитель ДОЛЖЕН иметь ВСЕ требуемые специализации
        Если хотя бы одна специализация отсутствует - возвращаем -1.0 (блокирующая оценка)
        """
        # Если у смены не указаны специализации - принимаем универсальных исполнителей
        if not shift.specialization_focus:
            return 0.5  # Нейтральная оценка для универсальных смен

        # Если у исполнителя нет специализаций - не подходит
        if not executor.specialization:
            logger.debug(f"Исполнитель {executor.id} не подходит: нет специализаций")
            return -1.0  # БЛОКИРУЮЩАЯ оценка

        # Преобразуем специализации в множества для сравнения
        required_specs = set(shift.specialization_focus)

        # Обрабатываем разные форматы хранения специализаций исполнителя
        if isinstance(executor.specialization, list):
            executor_specs = set(executor.specialization)
        elif isinstance(executor.specialization, str):
            import json
            try:
                executor_specs = set(json.loads(executor.specialization))
            except (json.JSONDecodeError, TypeError):
                executor_specs = {executor.specialization}
        else:
            executor_specs = set()

        # СТРОГАЯ ПРОВЕРКА: исполнитель ДОЛЖЕН иметь ВСЕ требуемые специализации
        missing_specs = required_specs - executor_specs

        if missing_specs:
            logger.debug(
                f"Исполнитель {executor.id} ({executor.first_name} {executor.last_name}) "
                f"не подходит для смены {shift.id}: отсутствуют специализации {missing_specs}. "
                f"Требуется: {required_specs}, Есть: {executor_specs}"
            )
            return -1.0  # БЛОКИРУЮЩАЯ оценка - нет нужных специализаций

        # Рассчитываем качество соответствия
        # Если у исполнителя есть ВСЕ требуемые специализации
        intersection = required_specs.intersection(executor_specs)

        # Базовая оценка - процент покрытия требований
        base_score = len(intersection) / len(required_specs) if required_specs else 0.0

        # Бонус за точное соответствие (нет лишних специализаций)
        if required_specs == executor_specs:
            base_score = 1.0  # Идеальное соответствие
        # Бонус за полное покрытие требований
        elif required_specs.issubset(executor_specs):
            base_score = 0.9  # Есть все нужные + дополнительные

        logger.debug(
            f"Исполнитель {executor.id} подходит для смены {shift.id}: "
            f"оценка специализации {base_score:.2f}"
        )

        return base_score

    def _calculate_workload_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает оценку на основе текущей загруженности исполнителя"""
        try:
            # Получаем активные смены исполнителя за неделю. Опорный день —
            # бизнес-дата смены (UTC-дата у ночной смены — вчерашняя), окно —
            # бизнес-сутки ±7 дней.
            base_day = business_date_of(shift.planned_start_time)
            win_start, win_end = business_days_window(
                base_day - timedelta(days=7), base_day + timedelta(days=7)
            )

            executor_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor.id,
                    Shift.planned_start_time >= win_start,
                    Shift.planned_start_time < win_end,
                    Shift.status.in_(['planned', 'active'])
                )
            ).count()

            # Получаем активные заявки исполнителя
            active_requests = self.db.query(Request).filter(
                and_(
                    Request.executor_id == executor.id,
                    Request.status.in_(['В работе', 'Принята', 'Закуп'])
                )
            ).count()

            # Рассчитываем балл загруженности (чем меньше нагрузка, тем выше балл)
            max_shifts_per_week = 7  # Максимум смен в неделю
            max_active_requests = 10  # Максимум активных заявок

            shift_load_score = max(0, (max_shifts_per_week - executor_shifts) / max_shifts_per_week)
            request_load_score = max(0, (max_active_requests - active_requests) / max_active_requests)

            return (shift_load_score + request_load_score) / 2

        except Exception as e:
            logger.error(f"Ошибка расчета загруженности для исполнителя {executor.id}: {e}")
            return 0.5  # Средняя оценка при ошибке

    def _calculate_rating_score(self, executor: User) -> float:
        """Рассчитывает оценку на основе рейтинга исполнителя"""
        if not hasattr(executor, 'rating') or executor.rating is None:
            return 0.5  # Средняя оценка для исполнителей без рейтинга

        # Нормализуем рейтинг от 0 до 1 (предполагаем рейтинг от 1 до 5)
        return min(1.0, max(0.0, (executor.rating - 1) / 4))

    def _calculate_availability_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает доступность исполнителя на время смены

        ИЗМЕНЕНО: Разрешаем перекрывающиеся смены с разными специализациями
        Один сотрудник может закрывать несколько компетенций одновременно
        """
        try:
            # Проверяем пересечения с другими сменами
            overlapping_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor.id,
                    Shift.id != shift.id,
                    Shift.status.in_(['planned', 'active']),
                    or_(
                        and_(
                            Shift.planned_start_time <= shift.planned_start_time,
                            Shift.planned_end_time > shift.planned_start_time
                        ),
                        and_(
                            Shift.planned_start_time < shift.planned_end_time,
                            Shift.planned_end_time >= shift.planned_end_time
                        )
                    )
                )
            ).all()

            # Проверяем пересечение специализаций - блокируем только если одинаковые
            if overlapping_shifts:
                # Получаем специализации текущей смены
                current_specs = shift.specialization_focus if shift.specialization_focus else []
                if isinstance(current_specs, str):
                    import json
                    try:
                        current_specs = json.loads(current_specs)
                    except Exception:
                        current_specs = [current_specs]

                # Проверяем каждую перекрывающуюся смену
                for overlapping_shift in overlapping_shifts:
                    overlap_specs = overlapping_shift.specialization_focus if overlapping_shift.specialization_focus else []
                    if isinstance(overlap_specs, str):
                        import json
                        try:
                            overlap_specs = json.loads(overlap_specs)
                        except Exception:
                            overlap_specs = [overlap_specs]

                    # Если есть пересечение специализаций - блокируем
                    common_specs = set(current_specs) & set(overlap_specs)
                    if common_specs:
                        logger.debug(
                            f"Блокировка назначения: смены имеют общие специализации {common_specs}"
                        )
                        return 0.0  # Блокируем только если одинаковые специализации

                    # BUG-138.4: лог по КАЖДОМУ фактическому перекрытию (раньше —
                    # один лог после цикла с overlap_specs последней итерации)
                    logger.debug(
                        f"Разрешено перекрытие смен: разные специализации "
                        f"(текущая: {current_specs}, перекрывающаяся: {overlap_specs})"
                    )

                # Если специализации разные - разрешаем, но с пониженной оценкой
                # (учитываем нагрузку на исполнителя)
                return 0.8  # Снижаем оценку из-за повышенной нагрузки

            # Проверяем минимальный отдых между сменами
            adjacent_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor.id,
                    Shift.id != shift.id,
                    Shift.status.in_(['planned', 'active', 'completed']),
                    or_(
                        # Смена заканчивается незадолго до начала новой
                        and_(
                            Shift.planned_end_time <= shift.planned_start_time,
                            Shift.planned_end_time > shift.planned_start_time - timedelta(hours=8)
                        ),
                        # Смена начинается вскоре после окончания новой
                        and_(
                            Shift.planned_start_time >= shift.planned_end_time,
                            Shift.planned_start_time < shift.planned_end_time + timedelta(hours=8)
                        )
                    )
                )
            ).first()

            if adjacent_shifts:
                return 0.7  # Сниженная доступность из-за недостаточного отдыха

            return 1.0  # Полная доступность

        except Exception as e:
            logger.error(f"Ошибка расчета доступности для исполнителя {executor.id}: {e}")
            return 0.5

    def _calculate_preference_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает соответствие предпочтениям исполнителя"""
        # Базовая реализация - можно расширить в будущем
        # Пока возвращаем нейтральную оценку
        return 0.5

    def _calculate_geographic_score(self, shift: Shift, executor: User) -> float:
        """Рассчитывает географическую близость исполнителя к зоне смены"""
        # Базовая реализация — фиксированный нейтральный балл
        return 0.5

    def _calculate_conflict_penalties(self, shift: Shift, executor: User) -> float:
        """Рассчитывает штрафы за конфликты назначения"""
        penalties = 0.0

        # Штраф за превышение максимальных смен в неделю (окно бизнес-дней
        # ±3 от бизнес-даты смены)
        base_day = business_date_of(shift.planned_start_time)
        win_start, win_end = business_days_window(
            base_day - timedelta(days=3), base_day + timedelta(days=3)
        )
        week_shifts = self.db.query(Shift).filter(
            and_(
                Shift.user_id == executor.id,
                Shift.planned_start_time >= win_start,
                Shift.planned_start_time < win_end,
                Shift.status.in_(['planned', 'active'])
            )
        ).count()

        if week_shifts >= 5:  # Много смен за неделю
            penalties += 0.3

        return penalties

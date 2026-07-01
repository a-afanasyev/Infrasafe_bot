import logging
from datetime import date, timedelta

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.services.shift_management_service import ShiftManagementService
from uk_management_bot.keyboards.shift_management import (
    get_planning_menu,
    get_analytics_menu,
)
from uk_management_bot.states.shift_management import ShiftManagementStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text

from ._router import router
from .shared import _db_scope, translate_specializations

logger = logging.getLogger(__name__)


@router.callback_query(F.data == "shift_analytics")
@require_role(['admin', 'manager'])
async def handle_shift_analytics(callback: CallbackQuery, state: FSMContext, db=None):
    """Меню аналитики смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.analytics_menu_title", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.analytics_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка аналитики: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "shift_executor_assignment")
@require_role(['admin', 'manager'])
async def handle_shift_executor_assignment(callback: CallbackQuery, state: FSMContext, db: Session = None, user: User = None, roles: list = None):
    """Назначение исполнителей для смен"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            # Получаем смены без назначенных исполнителей
            from datetime import datetime, timedelta
            now = datetime.now()
            week_ahead = now + timedelta(days=7)

            unassigned_shifts = ShiftManagementService(db).list_unassigned_planned_shifts_between(now, week_ahead)

            # BUG-BOT-014: используем клавиатуру с кнопкой "Назад" для возврата к меню смен
            from uk_management_bot.keyboards.shift_management import get_executor_assignment_keyboard

            if not unassigned_shifts:
                await callback.message.edit_text(
                    get_text("shift_management.no_unassigned_shifts", language=lang),
                    parse_mode="HTML",
                    reply_markup=get_executor_assignment_keyboard(lang)
                )
                await callback.answer()
                return

            # Показываем список смен для назначения

            shift_list = ""
            for shift in unassigned_shifts:
                start_time = shift.start_time.strftime('%d.%m.%Y %H:%M')
                # Переводим специализации на язык пользователя
                specialization_text = translate_specializations(shift.specialization_focus, lang)
                shift_list += f"🔹 <b>{start_time}</b> - {specialization_text}\n"

            text = get_text("shift_management.executor_assignment_list", language=lang,
                           count=len(unassigned_shifts),
                           shifts=shift_list)

            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_executor_assignment_keyboard(lang)
            )

            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка назначения исполнителей: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.executor_assignment_error", language=lang), show_alert=True)


@router.callback_query(F.data == "weekly_analytics")
@require_role(['admin', 'manager'])
async def handle_weekly_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Аналитика за неделю"""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Анализируем последние 7 дней
            end_date = date.today()
            start_date = end_date - timedelta(days=6)
        
            # Получаем комплексную аналитику
            analytics = await planning_service.get_comprehensive_analytics(
                start_date=start_date,
                end_date=end_date,
                include_recommendations=True
            )
        
            if 'error' in analytics:
                await callback.message.edit_text(
                    get_text("shift_management.analytics_error_msg", language=lang, error=analytics['error']),
                    reply_markup=get_analytics_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        
            # Build shift statistics section
            shift_stats = ""
            if analytics.get('shift_analytics'):
                sa = analytics['shift_analytics']
                shift_stats = get_text("shift_management.shift_stats_section", language=lang,
                                       total=sa.get('total_shifts', 0),
                                       avg_efficiency=sa.get('average_efficiency', 0),
                                       completion_rate=sa.get('completion_rate', 0),
                                       on_time_rate=sa.get('on_time_rate', 0))

            # Build planning efficiency section
            planning_stats = ""
            if analytics.get('planning_efficiency') and 'error' not in analytics['planning_efficiency']:
                pe = analytics['planning_efficiency']
                planning_stats = get_text("shift_management.planning_efficiency_section", language=lang,
                                          assignment_rate=pe.get('assignment_rate', 0),
                                          avg_duration=pe.get('avg_actual_duration', 0),
                                          unassigned=pe.get('unassigned_shifts', 0))

            # Build recommendations section
            recommendations_text = ""
            if analytics.get('recommendations'):
                recommendations = analytics['recommendations'][:3]
                no_description = get_text("shift_management.no_description", language=lang)
                rec_list = ""
                for i, rec in enumerate(recommendations, 1):
                    rec_text = rec.get('description', rec.get('recommendation', no_description))
                    rec_list += f"{i}. {rec_text[:100]}...\n"
                recommendations_text = get_text("shift_management.recommendations_section", language=lang,
                                              recommendations=rec_list)

            report = get_text("shift_management.weekly_analytics_report", language=lang,
                             start_date=start_date.strftime('%d.%m.%Y'),
                             end_date=end_date.strftime('%d.%m.%Y'),
                             total_days=analytics['period']['total_days'],
                             shift_stats=shift_stats,
                             planning_stats=planning_stats,
                             recommendations=recommendations_text)
        
            await callback.message.edit_text(
                report,
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка недельной аналитики: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.weekly_analytics_error", language=lang), show_alert=True)


@router.callback_query(F.data == "workload_forecast")
@require_role(['admin', 'manager'])
async def handle_workload_forecast(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Прогноз рабочей нагрузки"""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Прогноз на следующие 5 дней
            target_date = date.today() + timedelta(days=1)
            prediction = await planning_service.predict_workload(
                target_date=target_date,
                days_ahead=5
            )
        
            if 'error' in prediction:
                await callback.message.edit_text(
                    get_text("shift_management.forecast_error_msg", language=lang, error=prediction['error']),
                    reply_markup=get_analytics_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        
            # Формируем отчет прогноза
            forecast_period = prediction['forecast_period']
            summary = prediction['summary']

            # Build daily predictions list
            daily_list = ""
            requests_label = get_text("shift_management.requests_label", language=lang)
            confidence_label = get_text("shift_management.confidence_label", language=lang)
            for daily_pred in prediction['daily_predictions'][:5]:
                date_str = daily_pred['date'].strftime('%d.%m')
                requests = daily_pred['predicted_requests']
                load_level = daily_pred['load_level']
                confidence = daily_pred['confidence']

                load_emoji = {
                    'low': '🟢',
                    'medium': '🟡',
                    'high': '🔴'
                }.get(load_level, '⚪')

                daily_list += f"• {date_str}: {requests} {requests_label} {load_emoji} ({confidence_label}: {confidence:.0%})\n"

            # Build resource recommendations section
            resources_text = ""
            if summary.get('resource_requirements'):
                req = summary['resource_requirements']
                resources_text = get_text("shift_management.resource_recommendations_section", language=lang,
                                         daily_shifts=req['recommended_daily_shifts'],
                                         peak_shifts=req['peak_day_shifts'],
                                         min_executors=req['min_executors_needed'])

            # Build peak/low load days
            peak_days_text = ""
            if summary.get('peak_load_days'):
                peak_dates = [d.strftime('%d.%m') for d in summary['peak_load_days'][:3]]
                peak_days_text = f"\n{get_text('shift_management.peak_load_days', language=lang, dates=', '.join(peak_dates))}\n"

            low_days_text = ""
            if summary.get('low_load_days'):
                low_dates = [d.strftime('%d.%m') for d in summary['low_load_days'][:3]]
                low_days_text = f"{get_text('shift_management.low_load_days', language=lang, dates=', '.join(low_dates))}\n"

            report = get_text("shift_management.workload_forecast_report", language=lang,
                             start_date=forecast_period['start_date'].strftime('%d.%m.%Y'),
                             end_date=forecast_period['end_date'].strftime('%d.%m.%Y'),
                             avg_requests=summary['avg_predicted_requests'],
                             daily_list=daily_list,
                             resources=resources_text,
                             peak_days=peak_days_text,
                             low_days=low_days_text)
        
            await callback.message.edit_text(
                report,
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка прогноза нагрузки: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.workload_forecast_error", language=lang), show_alert=True)


@router.callback_query(F.data == "optimization_recommendations")
@require_role(['admin', 'manager'])
async def handle_optimization_recommendations(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Рекомендации по оптимизации"""
    try:
        with _db_scope(db) as db:
            planning_service = ShiftPlanningService(db)
            lang = get_user_language(callback.from_user.id, db)
        
            # Получаем рекомендации на сегодня
            recommendations = await planning_service.get_optimization_recommendations(
                target_date=date.today()
            )
        
            if 'error' in recommendations:
                await callback.message.edit_text(
                    get_text("shift_management.recommendations_error_msg", language=lang, error=recommendations['error']),
                    reply_markup=get_analytics_menu(lang),
                    parse_mode="HTML"
                )
                await callback.answer()
                return
        
            # Формируем отчет рекомендаций
            current_state = recommendations['current_state']
            target_date_str = recommendations['date'].strftime('%d.%m.%Y')

            # Build priority actions list
            priority_list = ""
            priority_actions = recommendations.get('priority_actions', [])
            if priority_actions:
                for action in priority_actions:
                    urgency_emoji = {
                        'high': '🔴',
                        'medium': '🟡',
                        'low': '🟢'
                    }.get(action.get('urgency', 'medium'), '⚪')

                    priority_list += f"{urgency_emoji} {action['description']}\n"
                    priority_list += f"   → {action['action']}\n\n"

            # Build optimization suggestions list
            optimization_list = ""
            optimization_suggestions = recommendations.get('optimization_suggestions', [])
            if optimization_suggestions:
                action_label = get_text("shift_management.action_label", language=lang)
                for suggestion in optimization_suggestions:
                    optimization_list += f"• {suggestion['description']}\n"
                    optimization_list += f"  {action_label}: {suggestion['action']}\n\n"

            # Build AI recommendations list
            ai_recs_list = ""
            if recommendations.get('ai_recommendations'):
                ai_recs = recommendations['ai_recommendations']
                if isinstance(ai_recs, dict) and ai_recs.get('recommendations'):
                    no_description = get_text("shift_management.no_description", language=lang)
                    for rec in ai_recs['recommendations'][:2]:
                        rec_text = rec.get('description', rec.get('recommendation', no_description))
                        ai_recs_list += f"• {rec_text[:80]}...\n"

            # All good message if no actions
            all_good_text = ""
            if not priority_actions and not optimization_suggestions:
                all_good_text = get_text("shift_management.optimization_all_good", language=lang)

            report = get_text("shift_management.optimization_recommendations_report", language=lang,
                             date=target_date_str,
                             total_shifts=current_state['shifts_count'],
                             assigned=current_state['assigned_shifts'],
                             unassigned=current_state['unassigned_shifts'],
                             priority_list=priority_list,
                             optimization_list=optimization_list,
                             ai_recs=ai_recs_list,
                             all_good=all_good_text)
        
            await callback.message.edit_text(
                report,
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )
        
            await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка рекомендаций по оптимизации: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.optimization_recommendations_error", language=lang), show_alert=True)


@router.callback_query(F.data == "monthly_analytics")
@require_role(['admin', 'manager'])
async def handle_monthly_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Месячный отчёт — заглушка (функция в разработке).

    Без этого handler-а кнопка `monthly_analytics` возвращала silent callback
    (no answer, no edit). См. BUG-BOT-003.
    """
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.monthly_analytics_under_development", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка месячного отчёта: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "efficiency_analysis")
@require_role(['admin', 'manager'])
async def handle_efficiency_analysis(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Анализ эффективности — заглушка (функция в разработке).

    Без этого handler-а кнопка `efficiency_analysis` возвращала silent callback
    (no answer, no edit). См. BUG-BOT-003.
    """
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.efficiency_analysis_under_development", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка анализа эффективности: {e}", exc_info=True)
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data == "back_to_planning")
async def handle_back_to_planning(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к меню планирования"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)
        
            await callback.message.edit_text(
                get_text("shift_management.planning_menu_title", language=lang),
                reply_markup=get_planning_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.planning_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к планированию: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.back_to_planning_error", language=lang), show_alert=True)


@router.callback_query(F.data == "back_to_analytics")
async def handle_back_to_analytics(callback: CallbackQuery, state: FSMContext, db=None, roles: list = None, user=None):
    """Возврат к меню аналитики"""
    try:
        with _db_scope(db) as db:
            lang = get_user_language(callback.from_user.id, db)

            await callback.message.edit_text(
                get_text("shift_management.analytics_menu_title", language=lang),
                reply_markup=get_analytics_menu(lang),
                parse_mode="HTML"
            )

            await state.set_state(ShiftManagementStates.analytics_menu)
            await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к аналитике: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shift_management.back_to_analytics_error", language=lang), show_alert=True)

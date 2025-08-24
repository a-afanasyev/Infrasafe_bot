"""
Google Sheets Integration Service

Этот модуль предоставляет функциональность для синхронизации данных
с Google Sheets в режиме реального времени.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from pathlib import Path

import structlog
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from uk_management_bot.config.settings import settings

logger = structlog.get_logger(__name__)


class SheetsServiceError(Exception):
    """Исключение для ошибок Google Sheets сервиса"""
    pass


class SyncTask:
    """Задача синхронизации с Google Sheets"""
    
    def __init__(self, task_type: str, request_id: int, data: Dict[str, Any], priority: str = "medium"):
        self.task_type = task_type  # "create", "update", "delete"
        self.request_id = request_id
        self.data = data
        self.priority = priority
        self.created_at = time.time()
        self.retry_count = 0
    
    def to_json(self) -> str:
        """Сериализация задачи в JSON"""
        return json.dumps({
            "task_type": self.task_type,
            "request_id": self.request_id,
            "data": self.data,
            "priority": self.priority,
            "created_at": self.created_at,
            "retry_count": self.retry_count
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SyncTask':
        """Десериализация задачи из JSON"""
        data = json.loads(json_str)
        task = cls(
            task_type=data["task_type"],
            request_id=data["request_id"],
            data=data["data"],
            priority=data["priority"]
        )
        task.created_at = data["created_at"]
        task.retry_count = data["retry_count"]
        return task


class SheetsService:
    """
    Сервис для работы с Google Sheets API
    
    Предоставляет методы для синхронизации заявок с Google Sheets
    в режиме реального времени.
    """
    
    def __init__(self):
        self.service = None
        self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        self.credentials_file = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.sync_enabled = settings.GOOGLE_SHEETS_SYNC_ENABLED
        
        # Названия листов в таблице
        self.requests_sheet_name = "Заявки"
        self.statistics_sheet_name = "Статистика"
        
        # Заголовки колонок для листа "Заявки"
        self.request_headers = [
            "ID заявки", "Дата создания", "Статус", "Категория", "Адрес",
            "Описание", "Срочность", "Заявитель ID", "Заявитель имя",
            "Исполнитель ID", "Исполнитель имя", "Дата назначения",
            "Дата выполнения", "Комментарии", "Фото ссылки",
            "Последнее обновление", "История изменений"
        ]
        
        if self.sync_enabled:
            self._initialize_service()
    
    def _initialize_service(self):
        """Инициализация Google Sheets API сервиса"""
        try:
            if not self.credentials_file or not Path(self.credentials_file).exists():
                logger.warning("Google Sheets credentials file not found", 
                             credentials_file=self.credentials_file)
                return
            
            # Загружаем credentials из файла
            credentials = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Создаем сервис
            self.service = build('sheets', 'v4', credentials=credentials)
            
            logger.info("Google Sheets service initialized successfully",
                       spreadsheet_id=self.spreadsheet_id)
            
        except Exception as e:
            logger.error("Failed to initialize Google Sheets service", 
                        error=str(e), credentials_file=self.credentials_file)
            raise SheetsServiceError(f"Failed to initialize Google Sheets service: {e}")
    
    async def test_connection(self) -> bool:
        """Тестирование подключения к Google Sheets"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not initialized")
                return False
            
            # Пытаемся получить информацию о таблице
            result = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            logger.info("Google Sheets connection test successful",
                       spreadsheet_title=result.get('properties', {}).get('title'))
            return True
            
        except HttpError as e:
            logger.error("Google Sheets connection test failed",
                        error=str(e), status_code=e.resp.status)
            return False
        except Exception as e:
            logger.error("Google Sheets connection test failed",
                        error=str(e))
            return False
    
    async def create_spreadsheet_structure(self) -> bool:
        """Создание структуры таблицы с необходимыми листами и заголовками"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not initialized")
                return False
            
            # Проверяем существование листов
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            existing_sheets = [sheet['properties']['title'] for sheet in spreadsheet['sheets']]
            
            # Создаем лист "Заявки" если его нет
            if self.requests_sheet_name not in existing_sheets:
                await self._create_requests_sheet()
            
            # Создаем лист "Статистика" если его нет
            if self.statistics_sheet_name not in existing_sheets:
                await self._create_statistics_sheet()
            
            logger.info("Google Sheets structure created successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to create Google Sheets structure",
                        error=str(e))
            return False
    
    async def _create_requests_sheet(self):
        """Создание листа 'Заявки' с заголовками"""
        try:
            # Добавляем новый лист
            add_sheet_request = {
                'addSheet': {
                    'properties': {
                        'title': self.requests_sheet_name,
                        'gridProperties': {
                            'rowCount': 1000,
                            'columnCount': len(self.request_headers)
                        }
                    }
                }
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': [add_sheet_request]}
            ).execute()
            
            # Добавляем заголовки
            header_range = f"{self.requests_sheet_name}!A1:{chr(65 + len(self.request_headers) - 1)}1"
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=header_range,
                valueInputOption='RAW',
                body={'values': [self.request_headers]}
            ).execute()
            
            logger.info("Requests sheet created successfully")
            
        except Exception as e:
            logger.error("Failed to create requests sheet", error=str(e))
            raise
    
    async def _create_statistics_sheet(self):
        """Создание листа 'Статистика'"""
        try:
            # Добавляем новый лист
            add_sheet_request = {
                'addSheet': {
                    'properties': {
                        'title': self.statistics_sheet_name,
                        'gridProperties': {
                            'rowCount': 100,
                            'columnCount': 4
                        }
                    }
                }
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': [add_sheet_request]}
            ).execute()
            
            # Добавляем заголовки
            header_range = f"{self.statistics_sheet_name}!A1:D1"
            headers = [["Метрика", "Значение", "Дата", "Время"]]
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=header_range,
                valueInputOption='RAW',
                body={'values': headers}
            ).execute()
            
            logger.info("Statistics sheet created successfully")
            
        except Exception as e:
            logger.error("Failed to create statistics sheet", error=str(e))
            raise
    
    async def find_request_row(self, request_id: int) -> Optional[int]:
        """Поиск строки заявки по ID"""
        try:
            if not self.service:
                return None
            
            # Получаем все данные из листа "Заявки"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.requests_sheet_name}!A:A"
            ).execute()
            
            values = result.get('values', [])
            
            # Ищем строку с нужным ID (пропускаем заголовок)
            for i, row in enumerate(values[1:], start=2):  # Начинаем с 2-й строки
                if row and str(row[0]) == str(request_id):
                    return i
            
            return None
            
        except Exception as e:
            logger.error("Failed to find request row", 
                        request_id=request_id, error=str(e))
            return None
    
    async def create_request_in_sheets(self, request_data: Dict[str, Any]) -> bool:
        """Создание новой заявки в Google Sheets"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not initialized")
                return False
            
            # Подготавливаем данные для вставки
            row_data = self._prepare_request_row_data(request_data)
            
            # Добавляем новую строку в конец таблицы
            range_name = f"{self.requests_sheet_name}!A:A"
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row_data]}
            ).execute()
            
            logger.info("Request created in Google Sheets successfully",
                       request_id=request_data.get('id'),
                       updated_cells=result.get('updates', {}).get('updatedCells'))
            
            return True
            
        except Exception as e:
            logger.error("Failed to create request in Google Sheets",
                        request_id=request_data.get('id'), error=str(e))
            return False
    
    async def update_request_in_sheets(self, request_id: int, changes: Dict[str, Any]) -> bool:
        """Обновление заявки в Google Sheets"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not initialized")
                return False
            
            # Находим строку заявки
            row_number = await self.find_request_row(request_id)
            if not row_number:
                logger.warning("Request not found in Google Sheets", request_id=request_id)
                return False
            
            # Подготавливаем данные для обновления
            update_data = self._prepare_update_data(changes)
            
            # Обновляем только измененные колонки
            for column_letter, value in update_data.items():
                range_name = f"{self.requests_sheet_name}!{column_letter}{row_number}"
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body={'values': [[value]]}
                ).execute()
            
            # Обновляем время последнего обновления
            last_updated_range = f"{self.requests_sheet_name}!P{row_number}"
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=last_updated_range,
                valueInputOption='RAW',
                body={'values': [[current_time]]}
            ).execute()
            
            logger.info("Request updated in Google Sheets successfully",
                       request_id=request_id, changes=list(changes.keys()))
            
            return True
            
        except Exception as e:
            logger.error("Failed to update request in Google Sheets",
                        request_id=request_id, error=str(e))
            return False
    
    def _prepare_request_row_data(self, request_data: Dict[str, Any]) -> List[str]:
        """Подготовка данных заявки для вставки в строку"""
        return [
            str(request_data.get('id', '')),
            request_data.get('created_at', ''),
            request_data.get('status', ''),
            request_data.get('category', ''),
            request_data.get('address', ''),
            request_data.get('description', ''),
            request_data.get('urgency', ''),
            str(request_data.get('applicant_id', '')),
            request_data.get('applicant_name', ''),
            str(request_data.get('executor_id', '')),
            request_data.get('executor_name', ''),
            request_data.get('assigned_at', ''),
            request_data.get('completed_at', ''),
            request_data.get('comments', ''),
            request_data.get('photo_urls', ''),
            time.strftime("%Y-%m-%d %H:%M:%S"),  # Последнее обновление
            ''  # История изменений
        ]
    
    def _prepare_update_data(self, changes: Dict[str, Any]) -> Dict[str, str]:
        """Подготовка данных для обновления"""
        # Маппинг полей на колонки (A=0, B=1, C=2, ...)
        field_to_column = {
            'status': 'C',
            'category': 'D',
            'address': 'E',
            'description': 'F',
            'urgency': 'G',
            'executor_id': 'J',
            'executor_name': 'K',
            'assigned_at': 'L',
            'completed_at': 'M',
            'comments': 'N',
            'photo_urls': 'O'
        }
        
        update_data = {}
        for field, value in changes.items():
            if field in field_to_column:
                column_letter = field_to_column[field]
                update_data[column_letter] = str(value)
        
        return update_data
    
    async def get_sync_status(self) -> Dict[str, Any]:
        """Получение статуса синхронизации"""
        return {
            "enabled": self.sync_enabled,
            "service_initialized": self.service is not None,
            "spreadsheet_id": self.spreadsheet_id,
            "credentials_file": self.credentials_file
        }


# Создаем глобальный экземпляр сервиса
sheets_service = SheetsService()

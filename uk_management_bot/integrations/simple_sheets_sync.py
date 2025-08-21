"""
Simple Google Sheets Integration (без API)

Простая интеграция с Google Sheets через публичный доступ
без использования Google Sheets API.
"""

import asyncio
import csv
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
import structlog
import os

logger = structlog.get_logger(__name__)


class SimpleSheetsSync:
    """
    Простая синхронизация с Google Sheets без API
    
    Использует публичный доступ к таблице через ссылку.
    """
    
    def __init__(self, spreadsheet_url: str, csv_file_path: str = "requests_export.csv"):
        """
        Инициализация простой синхронизации
        
        Args:
            spreadsheet_url: Публичная ссылка на Google Sheets
            csv_file_path: Путь к локальному CSV файлу для экспорта
        """
        self.spreadsheet_url = spreadsheet_url
        self.csv_file_path = csv_file_path
        self.sync_enabled = bool(spreadsheet_url)
        
        # Заголовки для CSV файла
        self.csv_headers = [
            "ID заявки", "Дата создания", "Статус", "Категория", "Адрес",
            "Описание", "Срочность", "Заявитель ID", "Заявитель имя",
            "Исполнитель ID", "Исполнитель имя", "Дата назначения",
            "Дата выполнения", "Комментарии", "Фото ссылки",
            "Последнее обновление", "История изменений"
        ]
        
        logger.info("SimpleSheetsSync initialized", 
                   spreadsheet_url=spreadsheet_url,
                   csv_file=csv_file_path)
    
    async def export_requests_to_csv(self, requests_data: List[Dict[str, Any]]) -> bool:
        """
        Экспорт заявок в CSV файл
        
        Args:
            requests_data: Список заявок для экспорта
            
        Returns:
            bool: True если экспорт успешен
        """
        try:
            # Создаем директорию если не существует
            csv_path = Path(self.csv_file_path)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Записываем данные в CSV
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Записываем заголовки
                writer.writerow(self.csv_headers)
                
                # Записываем данные заявок
                for request in requests_data:
                    row = self._prepare_request_row(request)
                    writer.writerow(row)
            
            logger.info("Requests exported to CSV successfully",
                       file_path=self.csv_file_path,
                       request_count=len(requests_data))
            
            return True
            
        except Exception as e:
            logger.error("Failed to export requests to CSV",
                        error=str(e), file_path=self.csv_file_path)
            return False
    
    async def add_request_to_csv(self, request_data: Dict[str, Any]) -> bool:
        """
        Добавление новой заявки в CSV файл
        
        Args:
            request_data: Данные заявки
            
        Returns:
            bool: True если добавление успешно
        """
        try:
            csv_path = Path(self.csv_file_path)
            
            # Создаем файл с заголовками если не существует
            if not csv_path.exists():
                with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(self.csv_headers)
            
            # Добавляем новую строку
            with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                row = self._prepare_request_row(request_data)
                writer.writerow(row)
            
            logger.info("Request added to CSV successfully",
                       request_id=request_data.get('id'),
                       file_path=self.csv_file_path)
            
            return True
            
        except Exception as e:
            logger.error("Failed to add request to CSV",
                        error=str(e), request_id=request_data.get('id'))
            return False
    
    async def update_request_in_csv(self, request_id: int, changes: Dict[str, Any]) -> bool:
        """
        Обновление заявки в CSV файле
        
        Args:
            request_id: ID заявки
            changes: Изменения для применения
            
        Returns:
            bool: True если обновление успешно
        """
        try:
            csv_path = Path(self.csv_file_path)
            
            if not csv_path.exists():
                logger.warning("CSV file not found", file_path=self.csv_file_path)
                return False
            
            # Читаем все данные
            rows = []
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
            
            if len(rows) < 2:  # Только заголовки
                logger.warning("CSV file is empty or has only headers")
                return False
            
            # Ищем строку с нужным ID
            found = False
            for i, row in enumerate(rows[1:], start=1):  # Пропускаем заголовки
                if row and str(row[0]) == str(request_id):
                    # Обновляем строку
                    updated_row = self._update_row_with_changes(row, changes)
                    rows[i] = updated_row
                    found = True
                    break
            
            if not found:
                logger.warning("Request not found in CSV", request_id=request_id)
                return False
            
            # Записываем обновленные данные
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(rows)
            
            logger.info("Request updated in CSV successfully",
                       request_id=request_id,
                       changes=list(changes.keys()))
            
            return True
            
        except Exception as e:
            logger.error("Failed to update request in CSV",
                        error=str(e), request_id=request_id)
            return False
    
    def _prepare_request_row(self, request_data: Dict[str, Any]) -> List[str]:
        """Подготовка данных заявки для записи в CSV"""
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
    
    def _update_row_with_changes(self, row: List[str], changes: Dict[str, Any]) -> List[str]:
        """Обновление строки с изменениями"""
        # Маппинг полей на индексы колонок
        field_to_index = {
            'status': 2,
            'category': 3,
            'address': 4,
            'description': 5,
            'urgency': 6,
            'executor_id': 9,
            'executor_name': 10,
            'assigned_at': 11,
            'completed_at': 12,
            'comments': 13,
            'photo_urls': 14
        }
        
        # Создаем копию строки
        updated_row = row.copy()
        
        # Применяем изменения
        for field, value in changes.items():
            if field in field_to_index:
                index = field_to_index[field]
                if index < len(updated_row):
                    updated_row[index] = str(value)
        
        # Обновляем время последнего обновления
        if 15 < len(updated_row):
            updated_row[15] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        return updated_row
    
    async def get_sync_status(self) -> Dict[str, Any]:
        """Получение статуса синхронизации"""
        csv_path = Path(self.csv_file_path)
        return {
            "enabled": self.sync_enabled,
            "spreadsheet_url": self.spreadsheet_url,
            "csv_file_path": self.csv_file_path,
            "csv_file_exists": csv_path.exists(),
            "csv_file_size": csv_path.stat().st_size if csv_path.exists() else 0
        }
    
    async def create_backup(self) -> str:
        """Создание резервной копии CSV файла"""
        try:
            csv_path = Path(self.csv_file_path)
            if not csv_path.exists():
                return ""
            
            # Создаем имя для backup файла
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = csv_path.parent / f"{csv_path.stem}_backup_{timestamp}.csv"
            
            # Копируем файл
            import shutil
            shutil.copy2(csv_path, backup_path)
            
            logger.info("CSV backup created successfully",
                       backup_path=str(backup_path))
            
            return str(backup_path)
            
        except Exception as e:
            logger.error("Failed to create CSV backup", error=str(e))
            return ""
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики CSV файла"""
        try:
            csv_path = Path(self.csv_file_path)
            if not csv_path.exists():
                return {"total_requests": 0, "file_size": 0}
            
            # Подсчитываем количество заявок
            request_count = 0
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
                request_count = max(0, len(rows) - 1)  # Исключаем заголовки
            
            return {
                "total_requests": request_count,
                "file_size": csv_path.stat().st_size,
                "last_modified": time.ctime(csv_path.stat().st_mtime)
            }
            
        except Exception as e:
            logger.error("Failed to get CSV statistics", error=str(e))
            return {"total_requests": 0, "file_size": 0}


# Создаем глобальный экземпляр
simple_sheets_sync = SimpleSheetsSync(
    spreadsheet_url=os.getenv("SIMPLE_SHEETS_URL", ""),
    csv_file_path=os.getenv("SIMPLE_SHEETS_CSV_PATH", "data/requests_export.csv")
)

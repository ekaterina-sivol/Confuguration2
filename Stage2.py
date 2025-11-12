#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей пакетов
Минимальный прототип с конфигурацией
"""

import configparser
import os
import sys
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse


class ConfigError(Exception):
    """Исключение для ошибок конфигурации"""
    pass


class DependencyGraphConfig:
    """Класс для работы с конфигурацией графа зависимостей"""

    def __init__(self, config_path: str = "config.ini"):
        self.config_path = config_path

    def load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из INI-файла"""
        config_parser = configparser.ConfigParser()

        # Проверка существования файла конфигурации
        if not os.path.exists(self.config_path):
            raise ConfigError(f"Конфигурационный файл '{self.config_path}' не найден")

        try:
            config_parser.read(self.config_path, encoding='utf-8')
        except configparser.Error as e:
            raise ConfigError(f"Ошибка чтения конфигурационного файла: {e}")

        # Проверка наличия обязательной секции
        if 'package' not in config_parser:
            raise ConfigError("В конфигурационном файле отсутствует секция 'package'")

        # Извлечение и валидация параметров
        package_section = config_parser['package']
        config = {}

        try:
            # Обязательные параметры
            config['name'] = self._get_required_parameter(package_section, 'name')
            config['version'] = self._get_required_parameter(package_section, 'version')
            config['repository_url'] = self._get_required_parameter(package_section, 'repository_url')

            # Опциональные параметры с значениями по умолчанию
            config['test_repository_mode'] = package_section.getboolean(
                'test_repository_mode',
                fallback=False
            )
            config['test_repository_path'] = package_section.get(
                'test_repository_path',
                fallback='./test_repo'
            )
            config['output_filename'] = package_section.get(
                'output_filename',
                fallback='dependency_graph.png'
            )
            config['ascii_tree_mode'] = package_section.getboolean(
                'ascii_tree_mode',
                fallback=False
            )
            config['package_filter'] = package_section.get(
                'package_filter',
                fallback=''
            )

        except (ValueError, configparser.NoOptionError) as e:
            raise ConfigError(f"Ошибка в параметрах конфигурации: {e}")

        # Дополнительная валидация
        self._validate_config(config)

        return config

    def _get_required_parameter(self, section: configparser.SectionProxy, param: str) -> str:
        """Получение обязательного параметра с проверкой"""
        value = section.get(param)
        if not value:
            raise ConfigError(f"Обязательный параметр '{param}' не указан или пуст")
        return value.strip()

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Валидация значений конфигурации"""

        # Проверка имени пакета
        if not config['name']:
            raise ConfigError("Имя пакета не может быть пустым")

        # Проверка версии
        if not config['version']:
            raise ConfigError("Версия пакета не может быть пустой")

        # Проверка URL репозитория
        repo_url = config['repository_url']
        if not repo_url:
            raise ConfigError("URL репозитория не может быть пустым")

        # Базовая проверка URL формата
        parsed_url = urlparse(repo_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ConfigError(f"Некорректный URL репозитория: {repo_url}")

        # Если включен тестовый режим, проверяем путь
        if config['test_repository_mode']:
            test_path = config['test_repository_path'].strip()
            if not test_path:
                raise ConfigError("Путь тестового репозитория не может быть пустым в тестовом режиме")

        # Проверка имени выходного файла
        output_file = config['output_filename'].strip()
        if not output_file:
            raise ConfigError("Имя выходного файла не может быть пустым")

        # Проверка расширения файла (должно быть изображением)
        valid_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.pdf'}
        file_ext = Path(output_file).suffix.lower()
        if file_ext not in valid_extensions:
            raise ConfigError(f"Неподдерживаемое расширение файла: {file_ext}. "
                              f"Допустимые: {', '.join(valid_extensions)}")


def print_config_summary(config: Dict[str, Any]) -> None:
    """Вывод сводки конфигурации в формате ключ-значение"""
    print("=" * 50)
    print("СВОДКА КОНФИГУРАЦИИ")
    print("=" * 50)

    for key, value in config.items():
        print(f"{key:<25}: {value}")

    print("=" * 50)


def main():
    """Основная функция приложения"""
    try:
        # Инициализация конфигурации
        config_manager = DependencyGraphConfig("config.ini")

        # Загрузка конфигурации
        config = config_manager.load_config()
        print("Конфигурация успешно загружена")

        # Вывод всех параметров конфигурации (требование этапа 1)
        print_config_summary(config)

        # Здесь будет дальнейшая логика анализа зависимостей
        print("\nГотово к анализу зависимостей!")
        print(f"Анализируемый пакет: {config['name']} {config['version']}")

        if config['ascii_tree_mode']:
            print("Режим ASCII-дерева: ВКЛЮЧЕН")

        if config['package_filter']:
            print(f"Фильтр пакетов: '{config['package_filter']}'")

    except ConfigError as e:
        print(f"Ошибка конфигурации: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
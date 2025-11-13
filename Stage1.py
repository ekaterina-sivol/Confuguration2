import configparser  # Парсинг INI-файлов конфигурации
import os  # Работа с файловой системой (проверка существования файлов)
import sys  # Системные функции (выход из программы, аргументы командной строки)
import argparse  # Парсинг аргументов командной строки
from pathlib import Path  # Объектно-ориентированная работа с путями файлов
from typing import Dict, Any  # Аннотации типов для лучшей читаемости кода

# Пользовательское исключение для ошибок конфигурации
# Наследуется от базового класса Exception
class ConfigError(Exception):
    pass
class DependencyGraphConfig:
    #Основной класс для работы с конфигурацией графа зависимостей.
    def __init__(self, config_path: str = "config.ini"):
        #Инициализация объекта конфигурации.
        self.config_path = config_path  # Сохраняем путь для последующего использования
        self.config = None  # Здесь будет храниться загруженная конфигурация
    def load_config(self) -> Dict[str, Any]:
        #Основной метод загрузки конфигурации из INI-файла.

        # Создаем экземпляр парсера INI-файлов
        config_parser = configparser.ConfigParser()

        # Проверка существования файла конфигурации ДО попытки чтения
        if not os.path.exists(self.config_path):
            raise ConfigError(f"Конфигурационный файл '{self.config_path}' не найден")

        try:
            # Чтение файла с явным указанием кодировки UTF-8
            config_parser.read(self.config_path, encoding='utf-8')
        except configparser.Error as e:
            # Ошибки парсинга INI-файла (неправильный формат, синтаксические ошибки)
            raise ConfigError(f"Ошибка чтения конфигурационного файла: {e}")
        except UnicodeDecodeError as e:
            # Ошибки кодировки (файл не в UTF-8)
            raise ConfigError(f"Ошибка кодировки конфигурационного файла: {e}")

        # Проверка наличия обязательной секции 'package'
        if 'package' not in config_parser:
            raise ConfigError("В конфигурационном файле отсутствует секция 'package'")

        # Получаем доступ к секции 'package' для извлечения параметров
        package_section = config_parser['package']
        config = {}  # Создаем пустой словарь для хранения конфигурации

        try:
            # Обязательные параметры

            # Имя пакета в формате groupId:artifactId
            config['name'] = self._get_required_parameter(package_section, 'name')
            # Версия пакета
            config['version'] = self._get_required_parameter(package_section, 'version')
            # URL Maven-репозитория для загрузки POM-файлов
            config['repository_url'] = self._get_required_parameter(package_section, 'repository_url')

            # Опциональные параметры

            # Режим тестирования: использование локальных файлов вместо удаленного репозитория
            config['test_repository_mode'] = self._get_boolean_parameter(
                package_section, 'test_repository_mode', False  # По умолчанию False
            )
            config['test_repository_path'] = package_section.get(
                'test_repository_path',
                fallback='./test_repo'  # Значение по умолчанию
            )

            # Имя файла для сохранения графа зависимостей
            config['output_filename'] = package_section.get(
                'output_filename',
                fallback='dependency_graph.png'  # Значение по умолчанию
            )

            # Режим отображения графа в виде ASCII-дерева в консоли
            config['ascii_tree_mode'] = self._get_boolean_parameter(
                package_section, 'ascii_tree_mode', False  # По умолчанию False
            )

            # Фильтр пакетов - строка для исключения определенных пакетов из анализа
            config['package_filter'] = package_section.get(
                'package_filter',
                fallback=''  # Пустая строка по умолчанию (без фильтрации)
            )

        except (ValueError, configparser.NoOptionError) as e:
            # Обработка ошибок получения параметров
            raise ConfigError(f"Ошибка в параметрах конфигурации: {e}")

        # Дополнительная валидация значений конфигурации
        self._validate_config(config)

        # Сохраняем конфигурацию в атрибуте объекта и возвращаем
        self.config = config
        return config

    def _get_required_parameter(self, section: configparser.SectionProxy, param: str) -> str:
        #Вспомогательный метод для получения обязательных параметров.
        # Проверяем наличие параметра в секции
        if param not in section:
            raise ConfigError(f"Обязательный параметр '{param}' отсутствует в конфигурационном файле")

        # Получаем значение параметра
        value = section.get(param)

        # Проверяем что значение не None, не пустая строка и не строка из пробелов
        if not value or not value.strip():
            raise ConfigError(f"Обязательный параметр '{param}' не указан или пуст")

        # Возвращаем значение, очищенное от начальных и конечных пробелов
        return value.strip()

    def _get_boolean_parameter(self, section: configparser.SectionProxy, param: str, default: bool) -> bool:
        #Вспомогательный метод для получения булевых параметров.

        # Если параметр отсутствует в секции, возвращаем значение по умолчанию
        if param not in section:
            return default

        value = section.get(param)

        # Если значение None, возвращаем значение по умолчанию
        if value is None:
            return default

        # Преобразование строкового значения в булево
        # Поддерживаемые значения для True
        if value.lower() in ('true', 'yes', '1', 'on'):
            return True
        # Поддерживаемые значения для False
        elif value.lower() in ('false', 'no', '0', 'off'):
            return False
        else:
            # Если значение не распознано, выбрасываем исключение с подсказкой
            raise ConfigError(
                f"Некорректное булево значение для параметра '{param}': '{value}'. "
                f"Ожидается: true/false, yes/no, 1/0, on/off")

    def _validate_config(self, config: Dict[str, Any]) -> None:

        # Проверка имени пакета
        name = config['name'].strip()
        if not name:
            raise ConfigError("Имя пакета не может быть пустым")

        if ':' not in name:
            raise ConfigError(f"Некорректный формат имени пакета: '{name}'. Ожидается: groupId:artifactId")

        # Проверка версии пакета
        version = config['version'].strip()
        if not version:
            raise ConfigError("Версия пакета не может быть пустой")

        # Проверка URL репозитория
        repo_url = config['repository_url'].strip()
        if not repo_url:
            raise ConfigError("URL репозитория не может быть пустым")

        # Базовая проверка корректности URL
        if not (repo_url.startswith('http://') or repo_url.startswith('https://')):
            raise ConfigError(f"Некорректный протокол URL репозитория: '{repo_url}'. Ожидается: http:// или https://")

        # Дополнительные проверки для тестового режима
        if config['test_repository_mode']:
            test_path = config['test_repository_path'].strip()
            if not test_path:
                raise ConfigError("Путь тестового репозитория не может быть пустым в тестовом режиме")

            # Проверка пути на наличие запрещенных символов
            invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
            for char in invalid_chars:
                if char in test_path:
                    raise ConfigError(f"Путь тестового репозитория содержит недопустимый символ: '{char}'")

        # Проверка имени выходного файла
        output_file = config['output_filename'].strip()
        if not output_file:
            raise ConfigError("Имя выходного файла не может быть пустым")

        # Проверка, что выходной файл имеет поддерживаемое расширение изображения
        valid_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.pdf'}
        file_ext = Path(output_file).suffix.lower()  # Извлекаем расширение файла
        if file_ext not in valid_extensions:
            raise ConfigError(f"Неподдерживаемое расширение файла: '{file_ext}'. "
                              f"Допустимые: {', '.join(valid_extensions)}")

        # Проверка типа фильтра пакетов
        package_filter = config['package_filter']
        if not isinstance(package_filter, str):
            raise ConfigError("Фильтр пакетов должен быть строкой")

def print_config_summary(config: Dict[str, Any]) -> None:
    print("-" * 50)
    print("СВОДКА КОНФИГУРАЦИИ")
    print("-" * 50)

    # Проходим по всем параметрам конфигурации
    for key, value in config.items():
        # Форматированный вывод
        print(f"{key:<25}: {value}")

    print("-" * 50)


def parse_arguments():
    #Функция для парсинга аргументов командной строки.

    # Создаем парсер аргументов с описанием
    parser = argparse.ArgumentParser(description='Этап 1: Загрузка и валидация конфигурации')

    # Добавляем аргумент для указания пути к конфигурационному файлу
    parser.add_argument(
        '-c', '--config',  # Короткое и длинное имя аргумента
        type=str,  # Тип значения
        default='config.ini',  # Значение по умолчанию
        help='Путь к конфигурационному файлу (по умолчанию: config.ini)'  # Текст помощи
    )

    return parser.parse_args()  # Парсим аргументы и возвращаем результат


def test_config_files():
    #Функция для тестирования различных конфигурационных файлов.

    # Список тестовых файлов для проверки
    test_files = [
        'config.ini',  # Полная корректная конфигурация
        'config_name.ini',  # Тест параметра name
        'config_version.ini',  # Тест параметра version
        'config_url.ini',  # Тест параметра repository_url
        'config_test_mode.ini',  # Тест тестового режима
        'config_ascii_mode.ini',  # Тест ASCII-режима
        'config_output.ini',  # Тест выходного файла
        'config_filter.ini'  # Тест фильтра пакетов
    ]

    print("ТЕСТИРОВАНИЕ КОНФИГУРАЦИОННЫХ ФАЙЛОВ")
    print("-" * 60)

    # Итерируемся по всем тестовым файлам
    for test_file in test_files:
        # Проверяем существование файла
        if os.path.exists(test_file):
            print(f"\nТестирование файла: {test_file}")
            print("-" * 40)
            try:
                # Создаем менеджер конфигурации для тестового файла
                config_manager = DependencyGraphConfig(test_file)
                # Пытаемся загрузить конфигурацию
                config = config_manager.load_config()
                print(" Конфигурация загружена успешно")
                # Выводим основные параметры для проверки
                print(f"   Пакет: {config['name']}")
                print(f"   Версия: {config['version']}")
            except ConfigError as e:
                # Ошибки конфигурации
                print(f" Ошибка конфигурации: {e}")
            except Exception as e:
                # Непредвиденные ошибки
                print(f" Непредвиденная ошибка: {e}")
        else:
            # Файл не найден
            print(f"\nФайл {test_file} не найден")


def main():
   # Основная функция приложения - точка входа.
    try:
        # Парсинг аргументов командной строки
        args = parse_arguments()
        # Специальная логика для тестирования
        if hasattr(args, 'test_all') and args.test_all:
            test_config_files()
            return

        # Инициализация менеджера конфигурации с указанным файлом
        config_manager = DependencyGraphConfig(args.config)
        # Загрузка конфигурации (может вызвать ConfigError)
        config = config_manager.load_config()
        # Вывод всех параметров конфигурации (основное требование этапа 1)
        print_config_summary(config)

    except ConfigError as e:
        # Обработка ошибок конфигурации с понятным сообщением
        print(f"Ошибка конфигурации: {e}")
        sys.exit(1)  # Выход с ненулевым кодом ошибки
    except KeyboardInterrupt:
        # Обработка прерывания пользователем (Ctrl+C)
        print("\nПрограмма прервана пользователем")
        sys.exit(1)
    except Exception as e:
        # Обработка всех непредвиденных ошибок
        print(f"Непредвиденная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
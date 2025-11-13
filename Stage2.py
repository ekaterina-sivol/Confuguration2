import configparser
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List
import urllib.request  # Для выполнения HTTP-запросов
import urllib.error  # Для обработки HTTP-ошибок
import xml.etree.ElementTree as ET  # Для парсинга XML-содержимого POM-файлов


# Пользовательское исключение для ошибок конфигурации
class ConfigError(Exception):
    pass
class DependencyGraphConfig:
    #Класс для работы с конфигурацией (практически идентичен Stage1).

    def __init__(self, config_path: str = "config.ini"):
        #Инициализация с путем к конфигурационному файлу
        self.config_path = config_path
        self.config = None

    def load_config(self) -> Dict[str, Any]:
        #Загрузка конфигурации из INI-файла
        config_parser = configparser.ConfigParser()

        # Проверка существования файла
        if not os.path.exists(self.config_path):
            raise ConfigError(f"Конфигурационный файл '{self.config_path}' не найден")

        try:
            # Чтение с указанием кодировки UTF-8
            config_parser.read(self.config_path, encoding='utf-8')
        except configparser.Error as e:
            raise ConfigError(f"Ошибка чтения конфигурационного файла: {e}")
        except UnicodeDecodeError as e:
            raise ConfigError(f"Ошибка кодировки конфигурационного файла: {e}")

        # Проверка обязательной секции
        if 'package' not in config_parser:
            raise ConfigError("В конфигурационном файле отсутствует секция 'package'")

        package_section = config_parser['package']
        config = {}

        try:
            # Обязательные параметры
            config['name'] = self._get_required_parameter(package_section, 'name')
            config['version'] = self._get_required_parameter(package_section, 'version')
            config['repository_url'] = self._get_required_parameter(package_section, 'repository_url')

            # Опциональные параметры
            config['test_repository_mode'] = self._get_boolean_parameter(
                package_section, 'test_repository_mode', False
            )
            config['test_repository_path'] = package_section.get(
                'test_repository_path',
                fallback='./test_repo'
            )
            config['output_filename'] = package_section.get(
                'output_filename',
                fallback='dependency_graph.png'
            )
            config['ascii_tree_mode'] = self._get_boolean_parameter(
                package_section, 'ascii_tree_mode', False
            )
            config['package_filter'] = package_section.get(
                'package_filter',
                fallback=''
            )

        except (ValueError, configparser.NoOptionError) as e:
            raise ConfigError(f"Ошибка в параметрах конфигурации: {e}")

        # Валидация конфигурации
        self._validate_config(config)
        self.config = config
        return config

    def _get_required_parameter(self, section: configparser.SectionProxy, param: str) -> str:
        #Получение обязательного параметра
        if param not in section:
            raise ConfigError(f"Обязательный параметр '{param}' отсутствует в конфигурационном файле")

        value = section.get(param)
        if not value or not value.strip():
            raise ConfigError(f"Обязательный параметр '{param}' не указан или пуст")
        return value.strip()

    def _get_boolean_parameter(self, section: configparser.SectionProxy, param: str, default: bool) -> bool:
        #Получение булевого параметра
        if param not in section:
            return default

        value = section.get(param)
        if value is None:
            return default

        if value.lower() in ('true', 'yes', '1', 'on'):
            return True
        elif value.lower() in ('false', 'no', '0', 'off'):
            return False
        else:
            raise ConfigError(
                f"Некорректное булево значение для параметра '{param}': '{value}'. Ожидается: true/false, yes/no, 1/0")

    def _validate_config(self, config: Dict[str, Any]) -> None:
        #Валидация значений конфигурации
        if not config['name'].strip():
            raise ConfigError("Имя пакета не может быть пустым")

        # Проверка формата имени пакета
        name = config['name'].strip()
        if ':' not in name:
            raise ConfigError(f"Некорректный формат имени пакета: '{name}'. Ожидается: groupId:artifactId")

        if not config['version'].strip():
            raise ConfigError("Версия пакета не может быть пустой")

        repo_url = config['repository_url'].strip()
        if not repo_url:
            raise ConfigError("URL репозитория не может быть пустым")

        # Проверка протокола URL
        if not (repo_url.startswith('http://') or repo_url.startswith('https://')):
            raise ConfigError(f"Некорректный протокол URL репозитория: '{repo_url}'. Ожидается: http:// или https://")

        # Дополнительные проверки для тестового режима
        if config['test_repository_mode']:
            test_path = config['test_repository_path'].strip()
            if not test_path:
                raise ConfigError("Путь тестового репозитория не может быть пустым в тестовом режиме")

        # Проверка имени выходного файла
        output_file = config['output_filename'].strip()
        if not output_file:
            raise ConfigError("Имя выходного файла не может быть пустым")

        # Проверка расширения файла
        valid_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.pdf'}
        file_ext = Path(output_file).suffix.lower()
        if file_ext not in valid_extensions:
            raise ConfigError(f"Неподдерживаемое расширение файла: '{file_ext}'. "
                              f"Допустимые: {', '.join(valid_extensions)}")


class DependencyFetcher:
    #Новый класс: Получение информации о зависимостях Maven-пакетов.

    def __init__(self, repository_url: str):
        #Инициализация загрузчика зависимостей.

        # Убираем конечный / для consistency URL
        self.repository_url = repository_url.rstrip('/')

    def get_dependencies(self, package_name: str, version: str) -> List[Dict[str, str]]:
        #Основной метод: получение прямых зависимостей пакета.

        # Парсим имя пакета на составляющие
        group_id, artifact_id = self._parse_package_name(package_name)

        # Строим URL для POM-файла
        pom_url = self._build_pom_url(group_id, artifact_id, version)

        try:
            # Выводим информационное сообщение о загрузке
            print(f"Загрузка POM из: {pom_url}")

            # Выполняем HTTP-запрос для получения POM-файла
            with urllib.request.urlopen(pom_url) as response:
                # Читаем и декодируем содержимое файла
                pom_content = response.read().decode('utf-8')

            # Парсим зависимости из содержимого POM-файла
            dependencies = self._parse_dependencies_from_pom(pom_content)
            return dependencies

        except urllib.error.HTTPError as e:
            # Обработка HTTP-ошибок
            if e.code == 404:
                # POM-файл не найден
                raise ConfigError(f"POM файл не найден по URL: {pom_url}")
            else:
                # Другие HTTP-ошибки
                raise ConfigError(f"Ошибка загрузки POM файла: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            # Ошибки сети
            raise ConfigError(f"Ошибка подключения к репозиторию: {e.reason}")
        except Exception as e:
            # Все остальные непредвиденные ошибки
            raise ConfigError(f"Ошибка обработки POM файла: {e}")

    def _parse_package_name(self, package_name: str) -> tuple[str, str]:
        #Парсинг имени пакета на groupId и artifactId.

        parts = package_name.split(':')
        if len(parts) != 2:
            raise ConfigError(f"Некорректный формат имени пакета: {package_name}. Ожидается: groupId:artifactId")
        return parts[0], parts[1]

    def _build_pom_url(self, group_id: str, artifact_id: str, version: str) -> str:
        #Построение URL для POM-файла по Maven-конвенции.

        # Преобразуем dots в slashes для groupId
        group_path = group_id.replace('.', '/')

        # Строим URL по Maven-конвенции
        return f"{self.repository_url}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"

    def _parse_dependencies_from_pom(self, pom_content: str) -> List[Dict[str, str]]:
        #Парсинг зависимостей из содержимого POM-файла.

        try:
            # Парсим XML из строки
            root = ET.fromstring(pom_content)

            # Проверка namespace POM-файла
            if not root.tag.startswith('{http://maven.apache.org/POM/'):
                raise ConfigError("Некорректный формат POM файла: отсутствует ожидаемый namespace")

            # Ищем секцию dependencies в POM-файле
            dependencies_elem = root.find('.//{http://maven.apache.org/POM/4.0.0}dependencies')

            # Если секция dependencies отсутствует, возвращаем пустой список
            if dependencies_elem is None:
                print("В POM файле не найдены зависимости")
                return []

            dependencies = []

            # Итерируемся по всем элементам dependency внутри секции dependencies
            for dep_elem in dependencies_elem.findall('{http://maven.apache.org/POM/4.0.0}dependency'):
                # Извлекаем groupId, artifactId и version для каждой зависимости
                group_id = dep_elem.find('{http://maven.apache.org/POM/4.0.0}groupId')
                artifact_id = dep_elem.find('{http://maven.apache.org/POM/4.0.0}artifactId')
                version_elem = dep_elem.find('{http://maven.apache.org/POM/4.0.0}version')

                # Проверяем что все обязательные элементы присутствуют и не пусты
                if (group_id is not None and artifact_id is not None and version_elem is not None and
                        group_id.text and artifact_id.text and version_elem.text):
                    # Формируем словарь с информацией о зависимости
                    dependencies.append({
                        'groupId': group_id.text.strip(),
                        'artifactId': artifact_id.text.strip(),
                        'version': version_elem.text.strip()
                    })

            # Выводим информационное сообщение о количестве найденных зависимостей
            print(f"Найдено зависимостей: {len(dependencies)}")
            return dependencies

        except ET.ParseError as e:
            # Ошибка парсинга XML
            raise ConfigError(f"Ошибка парсинга POM файла: {e}")


def print_config_summary(config: Dict[str, Any]) -> None:
    #Функция для вывода сводки конфигурации

    print("-" * 50)
    print("СВОДКА КОНФИГУРАЦИИ")
    print("-" * 50)

    for key, value in config.items():
        print(f"{key:<25}: {value}")

    print("-" * 50)


def parse_arguments():
    #Парсинг аргументов командной строки

    parser = argparse.ArgumentParser(description='Этап 2: Получение прямых зависимостей пакета')
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.ini',
        help='Путь к конфигурационному файлу (по умолчанию: config.ini)'
    )
    return parser.parse_args()


def main():
    #Основная функция приложения

    try:
        # Парсинг аргументов командной строки
        args = parse_arguments()

        # Загрузка конфигурации (унаследовано из Stage1)
        config_manager = DependencyGraphConfig(args.config)
        config = config_manager.load_config()
        print_config_summary(config)

        # Получение зависимостей
        print("\n" + "-" * 50)
        print("ПРЯМЫЕ ЗАВИСИМОСТИ ПАКЕТА")
        print("-" * 50)

        # Создаем загрузчик зависимостей с URL репозитория
        fetcher = DependencyFetcher(config['repository_url'])

        # Получаем зависимости для указанного пакета и версии
        dependencies = fetcher.get_dependencies(config['name'], config['version'])

        # Вывод результатов
        if dependencies:
            print(f"Найдено зависимостей: {len(dependencies)}")
            # Нумерованный список всех зависимостей
            for i, dep in enumerate(dependencies, 1):
                print(f"{i}. {dep['groupId']}:{dep['artifactId']}:{dep['version']}")
        else:
            print("Прямые зависимости не найдены")

        print("-" * 50)

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
import configparser
import os
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Any


class DependencyGraph:
    # Основной класс: Построение полного графа зависимостей Maven-пакетов.

    def __init__(self):

        #Инициализация графа зависимостей.
        self.graph: Dict[str, List[str]] = {}  # Основная структура графа
        self.visited: Set[str] = set()  # Посещенные узлы
        self.visiting: List[str] = []  # Текущий путь обхода (стек)
        self.cycles: Dict[str, Set[str]] = {}  # Обнаруженные циклы
        self.original_dependencies: Dict[str, List[str]] = {}  # Оригинальные зависимости

    def parse_config(self, config_path: str = "config.ini") -> Dict[str, Any]:
        #Упрощенный парсинг конфигурации для совместимости с этапами 1-2.

        config_parser = configparser.ConfigParser()

        if not os.path.exists(config_path):
            raise ValueError(f"Конфигурационный файл не найден: {config_path}")

        try:
            config_parser.read(config_path, encoding='utf-8')
        except Exception as e:
            raise ValueError(f"Ошибка чтения конфигурационного файла: {e}")

        if 'package' not in config_parser:
            raise ValueError("В конфигурационном файле отсутствует секция 'package'")

        package_section = config_parser['package']
        config = {}

        # Обязательные параметры
        required_params = ['name', 'version', 'repository_url']
        for param in required_params:
            if param not in package_section or not package_section[param].strip():
                raise ValueError(f"Обязательный параметр '{param}' отсутствует или пуст")
            config[param] = package_section[param].strip()

        # Опциональные параметры
        config['test_repository_mode'] = package_section.get('test_repository_mode', 'false').lower() in ('true', 'yes',
                                                                                                          '1', 'on')
        config['test_repository_path'] = package_section.get('test_repository_path', './test_repo')
        config['package_filter'] = package_section.get('package_filter', '')
        config['ascii_tree_mode'] = package_section.get('ascii_tree_mode', 'false').lower() in ('true', 'yes', '1',
                                                                                                'on')
        config['output_filename'] = package_section.get('output_filename', 'dependency_graph.png')

        return config

    def get_dependencies_from_pom(self, package_name: str, version: str, repository_url: str) -> List[str]:
        #Получение зависимостей из POM-файла

        group_id, artifact_id = self._parse_package_name(package_name)
        pom_url = self._build_pom_url(group_id, artifact_id, version, repository_url)

        try:
            print(f"Загрузка POM из: {pom_url}")
            with urllib.request.urlopen(pom_url) as response:
                pom_content = response.read().decode('utf-8')

            return self._parse_dependencies_from_pom(pom_content)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"POM файл не найден по URL: {pom_url}")
            else:
                raise ValueError(f"Ошибка загрузки POM файла: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            raise ValueError(f"Ошибка подключения к репозиторию: {e.reason}")
        except Exception as e:
            raise ValueError(f"Ошибка обработки POM файла: {e}")

    def _parse_package_name(self, package_name: str) -> tuple[str, str]:
        #Парсинг имени пакета на groupId и artifactId
        parts = package_name.split(':')
        if len(parts) != 2:
            raise ValueError(f"Некорректный формат имени пакета: {package_name}. Ожидается: groupId:artifactId")
        return parts[0], parts[1]

    def _build_pom_url(self, group_id: str, artifact_id: str, version: str, repository_url: str) -> str:
        #Построение URL для POM файла по Maven-конвенции
        group_path = group_id.replace('.', '/')
        repo_url = repository_url.rstrip('/')
        return f"{repo_url}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"

    def _parse_dependencies_from_pom(self, pom_content: str) -> List[str]:
        #Парсинг зависимостей из POM-файла.

        try:
            root = ET.fromstring(pom_content)

            # Проверка namespace POM файла
            if not root.tag.startswith('{http://maven.apache.org/POM/'):
                raise ValueError("Некорректный формат POM файла: отсутствует ожидаемый namespace")

            dependencies_elem = root.find('.//{http://maven.apache.org/POM/4.0.0}dependencies')
            if dependencies_elem is None:
                return []

            dependencies = []
            for dep_elem in dependencies_elem.findall('{http://maven.apache.org/POM/4.0.0}dependency'):
                group_id = dep_elem.find('{http://maven.apache.org/POM/4.0.0}groupId')
                artifact_id = dep_elem.find('{http://maven.apache.org/POM/4.0.0}artifactId')
                version_elem = dep_elem.find('{http://maven.apache.org/POM/4.0.0}version')

                if (group_id is not None and artifact_id is not None and
                        group_id.text and artifact_id.text):

                    # Формируем строку зависимости
                    dep_name = f"{group_id.text.strip()}:{artifact_id.text.strip()}"

                    # Добавляем версию, если она указана
                    if version_elem is not None and version_elem.text:
                        dep_name += f":{version_elem.text.strip()}"

                    dependencies.append(dep_name)

            return dependencies

        except ET.ParseError as e:
            raise ValueError(f"Ошибка парсинга POM файла: {e}")

    def read_dependencies_from_test_file(self, package_name: str, test_repo_path: str) -> List[str]:
        #Чтение зависимостей из тестового файла.

        try:
            if not os.path.exists(test_repo_path):
                raise ValueError(f"Тестовый файл не найден: {test_repo_path}")

            with open(test_repo_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Парсим файл построчно
            for line in content.split('\n'):
                line = line.strip()
                # Пропускаем пустые строки и комментарии
                if line and ':' in line and not line.startswith('#'):
                    parts = line.split(':', 1)  # Разделяем только по первому двоеточию
                    pkg = parts[0].strip()
                    # Если нашли нужный пакет
                    if pkg == package_name:
                        deps_str = parts[1].strip()
                        # Разделяем зависимости по запятым
                        dependencies = [dep.strip() for dep in deps_str.split(',') if dep.strip()]
                        return dependencies

            # Если пакет не найден, возвращаем пустой список
            return []

        except Exception as e:
            raise ValueError(f"Ошибка чтения тестового файла: {e}")

    def get_package_dependencies(self, package_name: str, version: str, repository_url: str, is_test_mode: bool) -> \
    List[str]:
        #Универсальная функция для получения зависимостей.
        if is_test_mode:
            # В тестовом режиме читаем из файла
            return self.read_dependencies_from_test_file(package_name, repository_url)
        else:
            # В реальном режиме загружаем из репозитория
            return self.get_dependencies_from_pom(package_name, version, repository_url)

    def _should_filter_package(self, package_name: str, package_filter: str) -> bool:
        #Проверка, нужно ли фильтровать пакет.

        if not package_filter:
            return False
        return package_filter in package_name

    def build_dependency_graph(self, package_name: str, version: str, repository_url: str,
                               is_test_mode: bool, package_filter: str = "",
                               depth: int = 0, max_depth: int = 10) -> None:

        #Основноц метод: Рекурсивное построение графа зависимостей с использованием DFS.

        #Защита обезвечивания: проверка максимальной глубины рекурсии
        if depth > max_depth:
            self.graph[package_name] = ["MAX_DEPTH_REACHED"]
            return

        #Фильтрация: проверка нужно ли фильтровать этот пакет
        if self._should_filter_package(package_name, package_filter):
            self.graph[package_name] = ["FILTERED"]
            return

        #Обнаружение циклов: проверка находится ли пакет в текущем пути обхода
        if package_name in self.visiting:
            # Найден цикл - вычисляем путь цикла
            cycle_start_index = self.visiting.index(package_name)
            cycle_path = self.visiting[cycle_start_index:] + [package_name]
            cycle_key = " -> ".join(cycle_path)

            # Сохраняем информацию о цикле для всех участвующих пакетов
            for node in cycle_path:
                if node not in self.cycles:
                    self.cycles[node] = set()
                self.cycles[node].add(cycle_key)

            # Добавляем пакет в граф если его еще нет
            if package_name not in self.graph:
                self.graph[package_name] = []
            return

        #Избежание повторного посещения: если пакет уже полностью обработан
        if package_name in self.visited:
            return

        #Добавление в текущий путь: помечаем пакет как обрабатываемый
        self.visiting.append(package_name)

        try:
            #Получение зависимостей: получаем зависимости текущего пакета
            dependencies = self.get_package_dependencies(package_name, version, repository_url, is_test_mode)

            #Сохранение оригинальных данных: сохраняем зависимости до обработки циклов
            self.original_dependencies[package_name] = dependencies.copy()

            #Добавление в граф: добавляем пакет и его зависимости в граф
            self.graph[package_name] = dependencies

            # Рекурсивный обход: обрабатываем каждую зависимость
            for dep in dependencies:
                dep_version = None if is_test_mode else version
                self.build_dependency_graph(dep, dep_version, repository_url, is_test_mode,
                                            package_filter, depth + 1, max_depth)

        except Exception as e:
            #Обработка ошибок: если не удалось получить зависимости
            self.graph[package_name] = [f"ERROR: {str(e)}"]

        finally:
            # Завершение обработки: удаляем из текущего пути и добавляем в посещенные
            self.visiting.remove(package_name)
            self.visited.add(package_name)

    def _process_cycles(self) -> None:
        #Обработка циклических зависимостей для специального отображения.

        processed_cycles = set()

        for node, cycle_set in self.cycles.items():
            if node in self.graph and cycle_set:
                # Формируем описание цикла
                cycle_desc = f"CYCLE: {list(cycle_set)[0]}"
                cycle_nodes = list(cycle_set)[0].split(" -> ")

                # Находим узел с минимальным алфавитным порядком в цикле
                # Этот узел будет отображать информацию о цикле
                first_cycle_node = min(cycle_nodes) if cycle_nodes else node

                # Если это первый узел цикла, заменяем его зависимости на описание цикла
                if node == first_cycle_node:
                    self.graph[node] = [cycle_desc]
                else:
                    # Для остальных узлов в цикле восстанавливаем оригинальные зависимости
                    if node in self.original_dependencies:
                        self.graph[node] = self.original_dependencies[node]

    def display_ascii_tree(self, start_package: str, prefix: str = "", is_last: bool = True) -> None:
        #Отображение графа в виде ASCII-дерева.

        # Определяем соединители для дерева
        connectors = "└── " if is_last else "├── "
        print(prefix + connectors + start_package)

        if start_package in self.graph:
            dependencies = self.graph[start_package]
            # Вычисляем новый префикс для следующего уровня
            new_prefix = prefix + ("    " if is_last else "│   ")

            for i, dep in enumerate(dependencies):
                is_last_dep = (i == len(dependencies) - 1)

                # Обработка специальных случаев (циклы, ошибки, фильтры)
                if dep.startswith("CYCLE:") or dep.startswith("ERROR:") or dep.startswith("FILTERED"):
                    connector = "└── " if is_last_dep else "├── "
                    print(new_prefix + connector + dep)
                else:
                    # Рекурсивный вызов для обычных зависимостей
                    if dep in self.graph and dep not in self.visited:
                        self.visited.add(dep)
                        self.display_ascii_tree(dep, new_prefix, is_last_dep)
                    else:
                        # Листовой узел или уже обработанный узел
                        connector = "└── " if is_last_dep else "├── "
                        print(new_prefix + connector + dep)

    def display_dependency_graph(self, ascii_mode: bool = False) -> None:
        #Вывод графа зависимостей в выбранном формате.

        print("\n" + "-" * 60)
        print("ГРАФ ЗАВИСИМОСТЕЙ")
        print("-" * 60)

        if ascii_mode:
            # Сохраняем и временно очищаем visited для ASCII отображения
            ascii_visited = self.visited.copy()
            self.visited.clear()

            # Определяем стартовый пакет для отображения
            start_package = next(iter(self.original_dependencies.keys())) if self.original_dependencies else next(
                iter(self.graph.keys()))
            self.display_ascii_tree(start_package)

            # Восстанавливаем visited
            self.visited = ascii_visited
        else:
            # Стандартный вывод в формате "пакет -> [зависимости]"
            sorted_packages = sorted(self.graph.keys())
            for package in sorted_packages:
                dependencies = self.graph[package]

                # Специальная обработка для циклических зависимостей
                if dependencies and len(dependencies) == 1 and dependencies[0].startswith("CYCLE:"):
                    print(f"{package} -> [{dependencies[0]}]")
                elif dependencies:
                    deps_str = ", ".join(dependencies)
                    print(f"{package} -> [{deps_str}]")
                else:
                    print(f"{package} -> []")

        # Статистика графа
        print(f"\nВсего пакетов в графе: {len(self.graph)}")
        if self.cycles:
            print(f"Обнаружено циклических зависимостей: {len(self.cycles)}")

    def create_test_files(self) -> None:
        #Создание тестовых файлов для демонстрации

        test_files = {
            "linear_tree.txt": """A: B, C
B: D
C: E
D: F
E: F
F:""",  # Простая иерархическая структура

            "cyclic_graph.txt": """A: B
B: C  
C: A
D: E
E:""",  # Циклическая зависимость A->B->C->A

             "diamond_graph.txt": """A: B, C
B: D
C: D
D: E
E:""",  # Ромбовидная структура зависимостей

            "complex_network.txt": """A: B, C, F
B: D, E
C: G
D: H
E: H, I
F: J
G: K
H: J
I: J
J: L
K: L
L:"""  # Сложная структура с множественными путями
        }

        # Создаем файлы если они не существуют
        for filename, content in test_files.items():
            if not os.path.exists(filename):
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Создан тестовый файл: {filename}")

    def get_all_packages_from_test_file(self, test_repo_path: str) -> List[str]:
        #Получает список всех пакетов из тестового файла.

        try:
            if not os.path.exists(test_repo_path):
                raise ValueError(f"Тестовый файл не найден: {test_repo_path}")

            with open(test_repo_path, 'r', encoding='utf-8') as f:
                content = f.read()

            packages = []
            for line in content.split('\n'):
                line = line.strip()
                # Извлекаем имена пакетов из каждой строки
                if line and ':' in line and not line.startswith('#'):
                    pkg = line.split(':', 1)[0].strip()
                    if pkg and pkg not in packages:
                        packages.append(pkg)

            return packages

        except Exception as e:
            raise ValueError(f"Ошибка чтения тестового файла: {e}")

    def build_complete_dependency_graph(self, repository_url: str, is_test_mode: bool) -> None:
        #Строит полный граф всех пакетов в репозитории.

        print("\nПостроение полного графа зависимостей...")

        if is_test_mode:
            # В тестовом режиме получаем все пакеты из файла
            all_packages = self.get_all_packages_from_test_file(repository_url)
            print(f"Найдено пакетов в тестовом файле: {len(all_packages)}")
        else:
            # В реальном режиме начинаем с пакета из конфигурации
            all_packages = [self.get_start_package_from_config()]

        total_packages = len(all_packages)

        # Строим граф для каждого пакета который еще не был посещен
        for package in all_packages:
            if package not in self.visited:
                self.build_dependency_graph(package, None, repository_url, is_test_mode)

        # Обрабатываем циклические зависимости
        self._process_cycles()

        print(f"Обработано пакетов: {len(self.visited)}/{total_packages}")
        print("Полный граф построен!")

    def get_start_package_from_config(self) -> str:
        #Получает стартовый пакет из конфигурации
        try:
            config = self.parse_config("config.ini")
            return config['name']
        except:
            return "com.example:A:1.0"  # Значение по умолчанию

    def interactive_test_mode(self) -> None:
        #Интерактивный режим тестирования.

        print("\n" + "-" * 50)
        print("ИНТЕРАКТИВНЫЙ РЕЖИМ ТЕСТИРОВАНИЯ")
        print("-" * 50)

        # Создаем тестовые файлы если их нет
        self.create_test_files()

        # Цикл выбора файла
        while True:
            file_path = input("\nВведите путь к тестовому файлу (например: test_simple.txt): ").strip()

            if not file_path:
                print("Путь не может быть пустым!")
                continue

            # Добавляем расширение если не указано
            if not file_path.endswith('.txt'):
                file_path += '.txt'

            if os.path.exists(file_path):
                break
            else:
                print(f"Файл '{file_path}' не найден!")
                print("Доступные тестовые файлы:")
                for file in ["test_simple.txt", "test_cycle.txt", "test_diamond.txt", "test_complex.txt"]:
                    if os.path.exists(file):
                        print(f"  - {file}")

        print(f"\nАнализируем файл {file_path}...")

        # Очищаем граф для нового анализа
        self.graph.clear()
        self.visited.clear()
        self.visiting.clear()
        self.cycles.clear()
        self.original_dependencies.clear()

        # Строим полный граф в тестовом режиме
        self.build_complete_dependency_graph(file_path, True)
        self.display_dependency_graph(False)  # Всегда стандартный вывод в интерактивном режиме


def main():
    #Основная функция приложения

    graph = DependencyGraph()

    # Проверка аргументов командной строки для интерактивного режима
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        graph.interactive_test_mode()
    else:
        try:
            # Загрузка конфигурации
            config = graph.parse_config("config.ini")

            print("=" * 50)
            print("ПОСТРОЕНИЕ ГРАФА ЗАВИСИМОСТЕЙ")
            print("=" * 50)
            print(f"Пакет: {config['name']}")
            print(f"Версия: {config['version']}")
            print(f"Режим тестирования: {config['test_repository_mode']}")
            print(f"Фильтр: {config['package_filter']}")

            # Построение графа зависимостей в зависимости от режима
            if config['test_repository_mode']:
                # В тестовом режиме строим полный граф из файла
                graph.build_complete_dependency_graph(config['test_repository_path'], True)
            else:
                # В реальном режиме строим граф для конкретного пакета
                graph.build_dependency_graph(
                    package_name=config['name'],
                    version=config['version'],
                    repository_url=config['repository_url'],
                    is_test_mode=False,
                    package_filter=config['package_filter']
                )
                # Обрабатываем циклические зависимости
                graph._process_cycles()

            # Вывод результатов в выбранном формате
            graph.display_dependency_graph(config['ascii_tree_mode'])

        except ValueError as e:
            print(f"Ошибка: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Неожиданная ошибка: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
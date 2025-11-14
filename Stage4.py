import configparser
import os
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Any
from collections import deque, defaultdict


class DependencyGraph:
    def __init__(self):
        self.graph: Dict[str, List[str]] = {}
        self.visited: Set[str] = set()
        self.visiting: List[str] = []
        self.cycles: Dict[str, Set[str]] = {}
        self.original_dependencies: Dict[str, List[str]] = {}

    def parse_config(self, config_path: str = "config.ini") -> Dict[str, Any]:
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

        required_params = ['name', 'version', 'repository_url']
        for param in required_params:
            if param not in package_section or not package_section[param].strip():
                raise ValueError(f"Обязательный параметр '{param}' отсутствует или пуст")
            config[param] = package_section[param].strip()

        config['test_repository_mode'] = package_section.get('test_repository_mode', 'false').lower() in ('true', 'yes',
                                                                                                          '1', 'on')
        config['test_repository_path'] = package_section.get('test_repository_path', './test_repo')
        config['package_filter'] = package_section.get('package_filter', '')
        config['ascii_tree_mode'] = package_section.get('ascii_tree_mode', 'false').lower() in ('true', 'yes', '1',
                                                                                                'on')
        config['output_filename'] = package_section.get('output_filename', 'dependency_graph.png')
        config['load_order_mode'] = package_section.get('load_order_mode', 'false').lower() in ('true', 'yes', '1',
                                                                                                'on')
        config['demo_mode'] = package_section.get('demo_mode', 'false').lower() in ('true', 'yes', '1', 'on')

        return config

    def get_dependencies_from_pom(self, package_name: str, version: str, repository_url: str) -> List[str]:
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
        parts = package_name.split(':')
        if len(parts) != 2:
            raise ValueError(f"Некорректный формат имени пакета: {package_name}. Ожидается: groupId:artifactId")
        return parts[0], parts[1]

    def _build_pom_url(self, group_id: str, artifact_id: str, version: str, repository_url: str) -> str:
        group_path = group_id.replace('.', '/')
        repo_url = repository_url.rstrip('/')
        return f"{repo_url}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}.pom"

    def _parse_dependencies_from_pom(self, pom_content: str) -> List[str]:
        try:
            root = ET.fromstring(pom_content)

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

                    dep_name = f"{group_id.text.strip()}:{artifact_id.text.strip()}"

                    if version_elem is not None and version_elem.text:
                        dep_name += f":{version_elem.text.strip()}"

                    dependencies.append(dep_name)

            return dependencies

        except ET.ParseError as e:
            raise ValueError(f"Ошибка парсинга POM файла: {e}")

    def read_dependencies_from_test_file(self, package_name: str, test_repo_path: str) -> List[str]:
        try:
            if not os.path.exists(test_repo_path):
                raise ValueError(f"Тестовый файл не найден: {test_repo_path}")

            with open(test_repo_path, 'r', encoding='utf-8') as f:
                content = f.read()

            for line in content.split('\n'):
                line = line.strip()
                if line and ':' in line and not line.startswith('#'):
                    parts = line.split(':', 1)
                    pkg = parts[0].strip()
                    if pkg == package_name:
                        deps_str = parts[1].strip()
                        dependencies = [dep.strip() for dep in deps_str.split(',') if dep.strip()]
                        return dependencies

            return []

        except Exception as e:
            raise ValueError(f"Ошибка чтения тестового файла: {e}")

    def get_package_dependencies(self, package_name: str, version: str, repository_url: str, is_test_mode: bool) -> \
            List[str]:
        if is_test_mode:
            return self.read_dependencies_from_test_file(package_name, repository_url)
        else:
            return self.get_dependencies_from_pom(package_name, version, repository_url)

    def _should_filter_package(self, package_name: str, package_filter: str) -> bool:
        if not package_filter:
            return False
        return package_filter in package_name

    def build_dependency_graph(self, package_name: str, version: str, repository_url: str,
                               is_test_mode: bool, package_filter: str = "",
                               depth: int = 0, max_depth: int = 10) -> None:

        if depth > max_depth:
            self.graph[package_name] = ["MAX_DEPTH_REACHED"]
            return

        if self._should_filter_package(package_name, package_filter):
            self.graph[package_name] = ["FILTERED"]
            return

        if package_name in self.visiting:
            cycle_start_index = self.visiting.index(package_name)
            cycle_path = self.visiting[cycle_start_index:] + [package_name]
            cycle_key = " -> ".join(cycle_path)

            for node in cycle_path:
                if node not in self.cycles:
                    self.cycles[node] = set()
                self.cycles[node].add(cycle_key)

            if package_name not in self.graph:
                self.graph[package_name] = []
            return

        if package_name in self.visited:
            return

        self.visiting.append(package_name)

        try:
            dependencies = self.get_package_dependencies(package_name, version, repository_url, is_test_mode)

            self.original_dependencies[package_name] = dependencies.copy()

            self.graph[package_name] = dependencies

            for dep in dependencies:
                dep_version = None if is_test_mode else version
                self.build_dependency_graph(dep, dep_version, repository_url, is_test_mode,
                                            package_filter, depth + 1, max_depth)

        except Exception as e:
            self.graph[package_name] = [f"ERROR: {str(e)}"]

        finally:
            self.visiting.remove(package_name)
            self.visited.add(package_name)

    def _process_cycles(self) -> None:
        processed_cycles = set()

        for node, cycle_set in self.cycles.items():
            if node in self.graph and cycle_set:
                cycle_desc = f"CYCLE: {list(cycle_set)[0]}"
                cycle_nodes = list(cycle_set)[0].split(" -> ")

                first_cycle_node = min(cycle_nodes) if cycle_nodes else node

                if node == first_cycle_node:
                    self.graph[node] = [cycle_desc]
                else:
                    if node in self.original_dependencies:
                        self.graph[node] = self.original_dependencies[node]

    def display_dependency_graph(self, ascii_mode: bool = False) -> None:
        print("\n" + "-" * 60)
        print("ГРАФ ЗАВИСИМОСТЕЙ")
        print("-" * 60)

        if ascii_mode:
            ascii_visited = self.visited.copy()
            self.visited.clear()

            start_package = next(iter(self.original_dependencies.keys())) if self.original_dependencies else next(
                iter(self.graph.keys()))
            self.display_ascii_tree(start_package)

            self.visited = ascii_visited
        else:
            sorted_packages = sorted(self.graph.keys())
            for package in sorted_packages:
                dependencies = self.graph[package]

                if dependencies and len(dependencies) == 1 and dependencies[0].startswith("CYCLE:"):
                    print(f"{package} -> [{dependencies[0]}]")
                elif dependencies:
                    deps_str = ", ".join(dependencies)
                    print(f"{package} -> [{deps_str}]")
                else:
                    print(f"{package} -> []")

        print(f"\nВсего пакетов в графе: {len(self.graph)}")
        if self.cycles:
            print(f"Обнаружено циклических зависимостей: {len(self.cycles)}")

    def create_test_files(self) -> None:
        test_files = {
            "linear_tree.txt": """A: B, C
B: D
C: E
D: F
E: F
F:""",

            "cyclic_graph.txt": """A: B
B: C  
C: A
D: E
E:""",

            "diamond_graph.txt": """A: B, C
B: D
C: D
D: E
E:""",

            "complex_dag.txt": """A: B, C, F
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
L:"""
        }

        for filename, content in test_files.items():
            if not os.path.exists(filename):
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Создан тестовый файл: {filename}")

    def get_all_packages_from_test_file(self, test_repo_path: str) -> List[str]:
        try:
            if not os.path.exists(test_repo_path):
                raise ValueError(f"Тестовый файл не найден: {test_repo_path}")

            with open(test_repo_path, 'r', encoding='utf-8') as f:
                content = f.read()

            packages = []
            for line in content.split('\n'):
                line = line.strip()
                if line and ':' in line and not line.startswith('#'):
                    pkg = line.split(':', 1)[0].strip()
                    if pkg and pkg not in packages:
                        packages.append(pkg)

            return packages

        except Exception as e:
            raise ValueError(f"Ошибка чтения тестового файла: {e}")

    def build_complete_dependency_graph(self, repository_url: str, is_test_mode: bool) -> None:
        print("\nПостроение полного графа зависимостей...")

        if is_test_mode:
            all_packages = self.get_all_packages_from_test_file(repository_url)
            print(f"Найдено пакетов в тестовом файле: {len(all_packages)}")
        else:
            all_packages = [self.get_start_package_from_config()]

        total_packages = len(all_packages)

        for package in all_packages:
            if package not in self.visited:
                self.build_dependency_graph(package, None, repository_url, is_test_mode)

        self._process_cycles()

        print(f"Обработано пакетов: {len(self.visited)}/{total_packages}")
        print("Полный граф построен!")

    def get_start_package_from_config(self) -> str:
        try:
            config = self.parse_config("config.ini")
            return config['name']
        except:
            return "com.example:A:1.0"

    def interactive_test_mode(self) -> None:
        print("\n" + "-" * 50)
        print("ИНТЕРАКТИВНЫЙ РЕЖИМ ТЕСТИРОВАНИЯ")
        print("-" * 50)

        self.create_test_files()

        while True:
            file_path = input("\nВведите путь к тестовому файлу ").strip()

            if not file_path:
                print("Путь не может быть пустым!")
                continue

            if not file_path.endswith('.txt'):
                file_path += '.txt'

            if os.path.exists(file_path):
                break
            else:
                print(f"Файл '{file_path}' не найден!")
                print("Доступные тестовые файлы:")
                for file in ["linear_tree.txt", "cyclic_graph.txt", "diamond_graph.txt", "complex_dag.txt"]:
                    if os.path.exists(file):
                        print(f"  - {file}")

        print(f"\nАнализируем файл {file_path}...")

        self.graph.clear()
        self.visited.clear()
        self.visiting.clear()
        self.cycles.clear()
        self.original_dependencies.clear()

        self.build_complete_dependency_graph(file_path, True)

        start_package = self.get_all_packages_from_test_file(file_path)[0]
        self.display_load_order(start_package)

    def calculate_load_order(self, start_package: str) -> List[str]:
        if not self.graph:
            raise ValueError("Граф зависимостей не построен")

        in_degree = defaultdict(int)
        reverse_graph = defaultdict(list)

        for package, dependencies in self.graph.items():
            if package not in in_degree:
                in_degree[package] = 0

            for dep in dependencies:
                if not (dep.startswith("CYCLE:") or dep.startswith("ERROR:") or
                        dep.startswith("FILTERED") or dep.startswith("MAX_DEPTH_REACHED")):
                    reverse_graph[dep].append(package)
                    in_degree[package] += 1

        queue = deque()
        load_order = []

        for package in self.graph:
            if in_degree[package] == 0:
                queue.append(package)

        while queue:
            current = queue.popleft()
            load_order.append(current)

            for dependent in reverse_graph[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(load_order) != len(self.graph):
            for package in self.graph:
                if package not in load_order:
                    load_order.append(package)

        return load_order

    def display_load_order(self, start_package: str) -> None:
        """
        Отображает порядок загрузки зависимостей в формате, похожем на пример.
        """
        print("\n" + "=" * 70)
        print("АНАЛИЗ ПОРЯДКА ЗАГРУЗКИ ДЛЯ ПАКЕТА:", start_package.upper())
        print("=" * 70)

        try:
            # Получаем зависимости для стартового пакета
            dependencies = []
            if start_package in self.graph:
                dependencies = [dep for dep in self.graph[start_package]
                                if not (dep.startswith("CYCLE:") or dep.startswith("ERROR:") or
                                        dep.startswith("FILTERED") or dep.startswith("MAX_DEPTH_REACHED"))]

            print(f"\nНайдено зависимостей для '{start_package.upper()}': {len(dependencies)} пакетов")

            # Рассчитываем порядок загрузки
            load_order = self.calculate_load_order(start_package)

            print("\nПОРЯДОК ЗАГРУЗКИ ЗАВИСИМОСТЕЙ:")
            print("-" * 40)

            for i, package in enumerate(load_order, 1):
                print(f"    {i}. {package}")

            print("\nОБЪЯСНЕНИЕ ПОРЯДКА:")
            print("-" * 40)
            print("Порядок основан на топологической сортировке графа зависимостей.")
            print("Каждый пакет загружается после всех своих зависимостей.")
            print("Это гарантирует, что при загрузке пакета все его зависимости уже доступны.")

            print("\nСРАВНЕНИЕ С РЕАЛЬНЫМИ МЕНЕДЖЕРАМИ ПАКЕТОВ:")
            print("-" * 40)
            print("В реальных менеджерах пакетов могут быть расхождения из-за:")
            print("1. Учета версий зависимостей")
            print("2. Разрешения конфликтов версий")
            print("3. Оптимизации для параллельной загрузки")
            print("4. Учета дополнительных метаданных пакетов")
            print("5. Поддержки альтернативных зависимостей")
            print("6. Кэширования уже загруженных пакетов")

            print("\nВЕРОЯТНЫЕ РАСХОЖДЕНИЯ:")
            print("-" * 40)
            print("Cargo (Rust): Может объединять одинаковые версии зависимостей")
            print("npm (Node.js): Использует плоскую структуру node_modules")
            print("pip (Python): Учитывает совместимость версий Python")
            print("Maven (Java): Учитывает scope зависимостей (compile/test/runtime)")

            print("\nАНАЛИЗ ЗАВЕРШЕН УСПЕШНО!")

        except Exception as e:
            print(f"Ошибка при расчете порядка загрузки: {e}")

    def demonstrate_on_test_cases(self) -> None:
        """
        Демонстрирует функциональность порядка загрузки на различных тестовых случаях.
        """
        print("\n" + "=" * 80)
        print("ДЕМОНСТРАЦИЯ ФУНКЦИОНАЛЬНОСТИ НА РАЗЛИЧНЫХ ТЕСТОВЫХ СЛУЧАЯХ")
        print("=" * 80)

        test_cases = [
            ("linear_tree.txt", "A", "Линейная иерархическая структура"),
            ("diamond_graph.txt", "A", "Ромбовидная структура зависимостей"),
            ("complex_dag.txt", "A", "Сложный направленный ациклический граф"),
            ("cyclic_graph.txt", "A", "Граф с циклическими зависимостями")
        ]

        for test_file, start_pkg, description in test_cases:
            if os.path.exists(test_file):
                print(f"\n{'=' * 60}")
                print(f"ТЕСТОВЫЙ СЛУЧАЙ: {description}")
                print(f"Файл: {test_file}, Стартовый пакет: {start_pkg}")
                print('=' * 60)

                self.graph.clear()
                self.visited.clear()
                self.visiting.clear()
                self.cycles.clear()
                self.original_dependencies.clear()

                try:
                    self.build_complete_dependency_graph(test_file, True)
                    self.display_load_order(start_pkg)
                except Exception as e:
                    print(f"Ошибка при обработке тестового файла: {e}")

                input("\nНажмите Enter для перехода к следующему тестовому случаю...")
            else:
                print(f"\nТестовый файл {test_file} не найден, пропускаем...")


def main():
    graph = DependencyGraph()

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        graph.interactive_test_mode()
    elif len(sys.argv) > 1 and sys.argv[1] == "--demo":
        graph.demonstrate_on_test_cases()
    else:
        try:
            config = graph.parse_config("config.ini")

            print("=" * 50)
            print("ПОСТРОЕНИЕ ГРАФА ЗАВИСИМОСТЕЙ - ЭТАП 4")
            print("=" * 50)
            print(f"Пакет: {config['name']}")
            print(f"Версия: {config['version']}")
            print(f"Режим тестирования: {config['test_repository_mode']}")
            print(f"Фильтр: {config['package_filter']}")

            if config['test_repository_mode']:
                graph.build_complete_dependency_graph(config['test_repository_path'], True)
            else:
                graph.build_dependency_graph(
                    package_name=config['name'],
                    version=config['version'],
                    repository_url=config['repository_url'],
                    is_test_mode=False,
                    package_filter=config['package_filter']
                )
                graph._process_cycles()

            print("\n" + "=" * 70)
            print("РЕЖИМ ПОРЯДКА ЗАГРУЗКИ (ЭТАП 4)")
            print("=" * 70)
            graph.display_load_order(config['name'])

        except ValueError as e:
            print(f"Ошибка: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Неожиданная ошибка: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
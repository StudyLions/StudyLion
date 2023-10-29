# Iterate through each file in the project
# Look for LocalBabel("text") in each file, mark it as the "text" domain
# module files inherit from their __init__ files if they don't specify a specific domain
import re
import os
from collections import defaultdict

babel_regex = re.compile(
    r".*LocalBabel\(\s*['\"](.*)['\"]\s*\).*"
)


ignored_dirs = {
    'RCS',
    '__pycache__',
    'pending-rewrite',
    '.git'
}


def parse_domain(path):
    """
    Parse a file to check for domain specifications.

    Currently just looks for a LocalBabel("domain") specification.
    """
    with open(path, 'r') as file:
        for line in file:
            match = babel_regex.match(line)
            if match:
                return match.groups()[0]


def read_directory(path, domain_map, domain='base'):
    init_path = None
    files = []
    dirs = []
    for entry in os.scandir(path):
        if entry.is_file(follow_symlinks=False) and entry.name.endswith('.py'):
            if entry.name == '__init__.py':
                init_path = entry.path
            else:
                files.append(entry.path)
        elif entry.is_dir(follow_symlinks=False) and entry.name not in ignored_dirs:
            dirs.append(entry.path)

    if init_path:
        domain = parse_domain(init_path) or domain
    print(
        f"{domain:<20} | {path}"
    )

    for file_path in files:
        file_domain = parse_domain(file_path) or domain
        print(
            f"{file_domain:<20} | {file_path}"
        )
        domain_map[file_domain].append(file_path)

    for dir_path in dirs:
        read_directory(dir_path, domain_map, domain)


def write_domains(domain_map):
    for domain, files in domain_map.items():
        domain_path = os.path.join('locales', 'domains', f"{domain}.txt")
        with open(domain_path, 'w') as domain_file:
            domain_file.write('\n'.join(files))
        print(f"Wrote {len(files)} source files to {domain_path}")


if __name__ == '__main__':
    domain_map = defaultdict(list)
    read_directory('src/', domain_map, domain='base')
    write_domains(domain_map)
    print("Supported domains: {}".format(', '.join(domain_map.keys())))

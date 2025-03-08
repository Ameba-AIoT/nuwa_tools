import importlib.metadata
import os
import platform

def read_requirements(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return [line.strip() for line in file if not line.startswith('#') and line.strip()]

def parse_requirement(requirement):
    parts = requirement.split('==')
    name = parts[0].strip()
    version = None if len(parts) < 2 else parts[1].strip()
    return name, version

def check_installed_packages(requirements):
    installed_packages = {dist.metadata['Name'].lower(): dist.version for dist in importlib.metadata.distributions()}
    missing_or_unsatisfied = []

    for requirement in requirements:

        if platform.system != 'Windows':
            if "windows-curses" in requirement:
                continue

        try:
            name, required_version = parse_requirement(requirement)
            if name.lower() in installed_packages:
                installed_version = installed_packages[name.lower()]
                if required_version and installed_version != required_version:
                    missing_or_unsatisfied.append(f"{name} {installed_version} does not satisfy {requirement}")
            else:
                missing_or_unsatisfied.append(f"{name} is not installed")
        except Exception as e:
            print(f"Error parsing requirement '{requirement}': {e}")

    return missing_or_unsatisfied

def main():
    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    requirements_file = os.path.join(script_dir, 'requirements.txt')
    requirements = read_requirements(requirements_file)
    issues = check_installed_packages(requirements)

    if issues:
        print("PIP CHECK... The following packages are not satisfied or not installed:")
        for issue in issues:
            print(issue)
        print('Please check your Internet connection and run:\r\n', f'pip install -r {requirements_file}')
    else:
        print("PIP CHECK... All packages are installed correctly!")

if __name__ == "__main__":
    main()


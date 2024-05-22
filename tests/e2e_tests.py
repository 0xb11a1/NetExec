import argparse
import os
import subprocess
from rich.console import Console
import platform

script_dir = os.path.dirname(os.path.abspath(__file__))
run_dir = os.path.dirname(os.path.abspath(__file__))
possible_locations = [
    os.path.join(run_dir, "tests/data/test_users.txt"),
    os.path.join(run_dir, "data/test_users.txt"),
]
test_user_file = next((loc for loc in possible_locations if os.path.isfile(loc)), None)
possible_locations = [
os.path.join(script_dir, "tests/data/test_passwords.txt"),
os.path.join(script_dir, "data/test_passwords.txt"),
]
test_password_file = next((loc for loc in possible_locations if os.path.isfile(loc)), None)


def get_cli_args():
    parser = argparse.ArgumentParser(description="Script for running end to end tests for nxc")
    parser.add_argument(
        "-t",
        "--target",
        dest="target",
        required=True
    )
    parser.add_argument(
        "-u",
        "--user",
        "--username",
        dest="username",
        required=True
    )
    parser.add_argument(
        "-p",
        "--pass",
        "--password",
        dest="password",
        required=True
    )
    parser.add_argument(
        "-k",
        "--kerberos",
        action="store_true",
        required=False,
        help="Use kerberos authentication",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        required=False,
        help="Display full command output",
    )
    parser.add_argument(
        "-e",
        "--errors",
        action="store_true",
        required=False,
        help="Display errors from commands",
    )
    parser.add_argument(
        "--poetry",
        action="store_true",
        required=False,
        help="Use poetry to run commands",
    )
    parser.add_argument(
        "--protocols",
        nargs="+",
        default=[],
        required=False,
        help="Protocols to test",
    )
    parser.add_argument(
        "--line-nums",
        nargs="+",
        type=parse_line_nums,
        required=False,
        help="Specify line numbers or ranges to run commands from",
    )
    parser.add_argument(
        "--print-failures",
        action="store_true",
        required=False,
        help="Prints all the commands of failed tests at the end",
    )
    parser.add_argument(
        "--test-user-file",
        dest="test_user_file",
        required=False,
        default=test_user_file,
        help="Path to the file containing test usernames",
    )
    parser.add_argument(
        "--test-password-file",
        dest="test_password_file",
        required=False,
        default=test_password_file,
        help="Path to the file containing test passwords",
    )
    parser.add_argument(
        "--dns-server",
        action="store",
        required=False,
        help="Specify DNS server",
    )
    return parser.parse_args()

def parse_line_nums(value):
    line_nums = []
    for item in value.split():
        if "-" in item:
            start, end = item.split("-")
            line_nums.extend(range(int(start), int(end) + 1))
        else:
            line_nums.append(int(item))
    return line_nums

def generate_commands(args):
    lines = []
    file_loc = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    commands_file = os.path.join(file_loc, "e2e_commands.txt")

    with open(commands_file) as file:
        if args.line_nums:
            flattened_list = list({num for sublist in args.line_nums for num in sublist})
            for i, line in enumerate(file):
                if i + 1 in flattened_list:
                    if line.startswith("#"):
                        continue
                    line = line.strip()
                    if args.protocols:
                        if line.split()[1] in args.protocols:
                            lines.append(replace_command(args, line))
                    else:
                        lines.append(replace_command(args, line))
        else:
            for line in file:
                if line.startswith("#"):
                    continue
                line = line.strip()
                if args.protocols:
                    if line.split()[1] in args.protocols:
                        lines.append(replace_command(args, line))
                else:
                    lines.append(replace_command(args, line))
    return lines

def replace_command(args, line):
    kerberos = "-k " if args.kerberos else ""
    dns_server = f"--dns-server {args.dns_server}" if args.dns_server else ""

    line = line\
        .replace("TARGET_HOST", args.target)\
        .replace("LOGIN_USERNAME", f'"{args.username}"')\
        .replace("LOGIN_PASSWORD", f'"{args.password}"')\
        .replace("KERBEROS ", kerberos)\
        .replace("TEST_USER_FILE", args.test_user_file)\
        .replace("TEST_PASSWORD_FILE", args.test_password_file)\
        .replace("{DNS}", dns_server)
    if args.poetry:
        line = f"poetry run {line}"
    return line


def run_e2e_tests(args):
    console = Console()
    tasks = generate_commands(args)
    failures = []

    result = subprocess.Popen(
        "netexec --version",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    version = result.communicate()[0].decode().strip()

    with console.status(f"[bold green] :brain: Running {len(tasks)} test commands for nxc v{version}..."):
        passed = 0
        failed = 0

        while tasks:
            task = str(tasks.pop(0))
            # replace double quotes with single quotes for Linux due to special chars/escaping
            if platform.system() == "Linux":
                task = task.replace('"', "'")
            # we print the command before running because very often things will timeout and we want the last thing ran
            console.log(f"Running command: {task}")
            result = subprocess.Popen(
                task,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            # pass in a "y" for things that prompt for it (--ndts, etc)
            text = result.communicate(input=b"y")[0]
            return_code = result.returncode

            if return_code == 0:
                console.log(f"{task.strip()} :heavy_check_mark:")
                passed += 1
            else:
                console.log(f"[bold red]{task.strip()} :cross_mark:[/]")
                failures.append(task.strip())
                failed += 1

            if args.errors:
                raw_text = text.decode("utf-8")
                # this is not a good way to detect errors, but it does catch a lot of things
                if "error" in raw_text.lower() or "failure" in raw_text.lower():
                    console.log("[bold red]Error Detected:")
                    console.log(f"{raw_text}")

            if args.verbose:
                # this prints sorta janky, but it does its job
                console.log(f"[*] Results:\n{text.decode('utf-8')}")
        

        if args.print_failures and failures:
            console.log("[bold red]Failed Commands:")
            for failure in failures:
                console.log(f"[bold red]{failure}")
        console.log(f"Tests [bold green] Passed: {passed} [bold red] Failed: {failed}")


if __name__ == "__main__":
    parsed_args = get_cli_args()
    run_e2e_tests(parsed_args)

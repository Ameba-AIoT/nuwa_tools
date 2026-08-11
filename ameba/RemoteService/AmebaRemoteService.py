#! /usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (c) 2024 Realtek Semiconductor Corp.
# SPDX-License-Identifier: Apache-2.0

import socket
import subprocess
import sys
import ctypes
import threading
import time
import datetime
import serial
import serial.tools.list_ports
import json
import logging
import base64
from typing import List, Dict, Optional
from dataclasses import dataclass
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
from infi.systray import SysTrayIcon
import os
import re
import shlex
import argparse
import winreg
from version_manager import version

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "AmebaRemoteService"

APP_NAME = "AmebaRemoteService"
APP_VERSION = f"v{version}"
PORT = 58916
MAX_CONNECTIONS = 10
OPENOCD_PORTS = [58920, 58921, 58922]
log_levels = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARN": logging.WARN, "ERROR": logging.ERROR}

@dataclass
class SerialConfig:
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "none"

@dataclass
class ClientInfo:
    addr: tuple
    serials: List[str]
    thread: threading.Thread
    validate: bool

def resource_path(rel_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel_path)
    # For non-frozen mode, use the script's directory as base
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, rel_path)

CONFIG_FILE = "config.json"

def load_config():
    default_config = {
        "password": "",
        "log_level": "INFO"
    }

    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load config: {e}")
        return default_config

def save_config(password, log_level):
    config_data = {
        "password": password,
        "log_level": log_level
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Failed to save config: {e}")

def get_autostart_exe_path():
    """Get the executable path for autostart."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return sys.executable

def is_autostart_enabled() -> bool:
    """Check if auto-start is enabled in registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

def enable_autostart() -> bool:
    """Enable auto-start on Windows login."""
    try:
        exe_path = get_autostart_exe_path()
        if getattr(sys, 'frozen', False):
            # Windowed exe (console=False): no console window, pass args directly
            cmd = f'"{exe_path}" --minimized'
        else:
            cmd = f'"{exe_path}" "{os.path.abspath(__file__)}" --minimized'

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0,
                           winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        return True
    except Exception as e:
        print(f"Failed to enable autostart: {e}")
        return False

def disable_autostart() -> bool:
    """Disable auto-start on Windows login."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0,
                           winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, AUTOSTART_NAME)
        return True
    except FileNotFoundError:
        # Key doesn't exist, already disabled
        return True
    except Exception as e:
        print(f"Failed to disable autostart: {e}")
        return False

class AmebaSerialServer:
    def __init__(self):
        # Initialize logger
        self.logger = self._setup_logger()
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.connected_clients: Dict[socket.socket, ClientInfo] = {}
        self.open_serials: Dict[str, serial.Serial] = {}
        self.port_owners: Dict[str, dict] = {}  # port -> {"source": str, "client_socket": socket}
        self.serial_lock = threading.Lock()
        self.tcp_lock = threading.Lock()
        self.start_time = time.time()
        self.cur_time = 0
        self.total_bytes = 0
        self.password = ""
        self.openocd_process = None
        self.openocd_cmds = []
        self.msg_queue = queue.Queue()

    def _setup_logger(self) -> logging.Logger:
        """Set up and return a Logger object"""
        logger = logging.getLogger(APP_NAME)
        logger.setLevel(logging.INFO)  # Set log level to DEBUG to capture all levels

        if not logger.handlers:
            # Output to console
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

            # (Optional) Output to file
            # file_handler = logging.FileHandler(f"{APP_NAME}.log")
            # file_handler.setFormatter(formatter)
            # logger.addHandler(file_handler)
        return logger

    def getLevelName(self, level):
        current_level_name = "INFO" 
        for name, level in log_levels.items():
            if self.logger.level == level:
                current_level_name = name
                break
        return current_level_name

    # --- Firewall Related Methods ---
    def is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def _run_netsh(self, command):
        try:
            full_cmd = f"chcp 65001 >nul && netsh advfirewall firewall {command}"
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.stdout
        except Exception:
            return ""

    def clean_firewall_rules(self, targets: List):
        for name in targets:
            self.logger.info(f"[*] Fast cleaning '{name}' Firewall rules...")
            output = self._run_netsh(f'delete rule name="{name}"')

            match = re.search(r'(\d+)', output)
            if match and "0" not in match.group(1):
                count = match.group(1)
                self.logger.info(f"Delete '{name}' success, deleted {count} rules")
                self.logger.info("OK.")
            else:
                self.logger.warning(f"No '{name}' matched rules")

    def setup_firewall(self) -> bool:
        self.logger.info("Checking firewall settings...")
        ports = [PORT]
        ports.extend(OPENOCD_PORTS)

        targets = [f'AmebaSerialServer_v1.0.4_{p}' for p in ports]
        self.clean_firewall_rules(targets)

        def _setup_firewall(port):
            firewall_name = f'{APP_NAME}_{port}'
            try:
                subprocess.run(
                    ['netsh', 'advfirewall', 'firewall', 'show', 'rule', f'name={firewall_name}'],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.logger.info(f"Firewall rule '{firewall_name}' already exists.")
                return True
            except subprocess.CalledProcessError:
                self.logger.info(f"Adding new firewall rule '{firewall_name}'...")

            add_cmd = [
                'netsh', 'advfirewall', 'firewall', 'add', 'rule',
                f'name={firewall_name}', 'dir=in', 'action=allow',
                'protocol=TCP', f'localport={port}'
            ]
            try:
                subprocess.run(add_cmd, check=True, capture_output=True, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
                self.logger.info(f"Firewall rule '{firewall_name}' added successfully.")
                return True
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to add firewall rule: {e.stderr}")
                return False
            except FileNotFoundError:
                self.logger.error("Error: 'netsh' command not found (may not be a Windows environment).")
                return False
        for port in ports:
            _setup_firewall(port)

    # --- TCP Server ---
    def start_server(self, main_app):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind(('0.0.0.0', PORT))
            self.server_socket.listen(MAX_CONNECTIONS)
            self.logger.info(f"TCP Server started, listening on port {PORT}...")

            while self.running:
                try:
                    client_socket, client_addr = self.server_socket.accept()
                    with self.tcp_lock:
                        self.logger.info(f"New connection: {client_addr[0]}:{client_addr[1]}")
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        self.logger.info(f"Set TCP_NODELAY for {client_addr}")

                        client_thread = threading.Thread(
                            target=self.handle_client,
                            args=(client_socket, client_addr),
                            daemon=True
                        )
                        client_validate = True
                        if self.password != "":
                            client_validate = False
                        self.connected_clients[client_socket] = ClientInfo(client_addr, serials=[], thread=client_thread, validate=client_validate)
                        client_thread.start()
                except OSError:
                    if self.running:
                        self.logger.info("Server Socket closed, stopping accepting new connections.")
                    break
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error occurred while accepting connection", exc_info=True)
                    break
        except OSError as e:
            self.logger.critical(f"Failed to start Server: {e} (Port may already be occupied)")
            self.stop_server()
            self.logger.info("Shutting down program after 3 secs...")
            time.sleep(3)
            if main_app:
                main_app.after(0, main_app.quit_app)

    def stop_server(self):
        if not self.running:
            return
        self.running = False
        self.logger.info("Shutting down the server...")
        self.stop_openocd()
        # close Server Socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                self.logger.error(f"Error occurred while closing server socket", exc_info=True)

        # Close all client connections
        with self.tcp_lock:
            for client_socket in list(self.connected_clients.keys()):
                try:
                    client_socket.close()
                except Exception as e:
                    self.logger.error(f"Error occurred while closing client", exc_info=True)
            self.connected_clients.clear()

        # Close all serial ports
        with self.serial_lock:
            for port, ser in self.open_serials.items():
                try:
                    if ser.is_open:
                        ser.close()
                        self.logger.info(f"Serial port {port} closed.")
                except Exception as e:
                    self.logger.error(f"Error occurred while closing serial port {port}", exc_info=True)
            self.open_serials.clear()

        self.logger.info("Server has been closed successfully.")

    def handle_client(self, client_socket: socket.socket, client_addr: tuple):
        buffer = ""
        addr_str = f"{client_addr[0]}:{client_addr[1]}"
        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    self.logger.info(f"Client disconnected: {addr_str}")
                    break

                buffer += data.decode('utf-8', errors='ignore')
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    message_str = message_str.strip()
                    if message_str:
                        result = self.process_client_command(client_socket, message_str)
                        if not result:
                            raise ConnectionAbortedError
        except (ConnectionResetError, ConnectionAbortedError):
            self.logger.info(f"Client connection interrupted: {addr_str}")
        except Exception as e:
            if self.running:
                self.logger.error(f"Unknown error while handling client {addr_str}")
        finally:
            with self.tcp_lock:
                client = self.connected_clients.pop(client_socket, None)
                self.logger.info(f"Client disconnected pop: {addr_str}")
            if client:
                for port in client.serials:
                    self.close_serial_port(port)
            try:
                client_socket.close()
            except:
                pass

    def _monitor_openocd_output(self, process, client_socket):
        try:
            for line in process.stdout:
                if line:
                    log_content = line.strip()
                    if log_content:
                        self.logger.info(f"[OpenOCD] {log_content}")
        except Exception as e:
            self.logger.error(f"OpenOCD Monitor Error: {e}")
        finally:
            self.logger.info("OpenOCD Monitor Thread Stopped")
            response = {
                "type": "terminate",
                "message": "OpenOCD terminated"
            }
            self.send_to_client(client_socket, response)

    def start_openocd(self, cmds, client_socket):
        if self.openocd_process:
            self.stop_openocd()
        success = False
        try:
            self.openocd_process = subprocess.Popen(cmds,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        )
            self.openocd_cmds = cmds
            monitor_thread = threading.Thread(
                target=self._monitor_openocd_output, 
                args=(self.openocd_process, client_socket),
                daemon=True
            )
            monitor_thread.start()

            time.sleep(0.2)
            self.logger.info("OpenOCD status check...")
            if self.openocd_process.poll() is not None:
                self.logger.error("OpenOCD exited immediately after start.")
                success = False
                self.openocd_process = None
            else:
                # self.clean_firewall_rules( targets = ["openocd", "openocd.exe"])
                # threading.Thread(target=self.clean_firewall_rules, daemon=True).start()
                self.logger.info("OpenOCD Process Started Successfully (PID: {})".format(self.openocd_process.pid))
                success = True
        except Exception as e:
            self.logger.error(f"OpenOCD Start Failed: {e}")
        if not success:
            self.stop_openocd()
        return success

    def stop_openocd(self):
        if hasattr(self, 'openocd_process') and self.openocd_process:
            self.logger.info(f"Stop OpenOCD (PID: {self.openocd_process.pid})...")
            pid = self.openocd_process.pid
            self.openocd_process.terminate()
            try:
                self.openocd_process.wait(timeout=0.5)
                self.logger.info("OpenOCD Process Stopped Successfully (PID: {})".format(pid))
            except subprocess.TimeoutExpired:
                self.logger.warning("OpenOCD response timeout, forcibly stopping ...")
                self.openocd_process.kill()
                self.openocd_process.wait()
                self.logger.info("OpenOCD force stopped")
            self.openocd_process = None

    def process_client_command(self, client_socket: socket.socket, command_str: str):
        self.logger.debug(f"Received command: {command_str}")
        response = None
        try:
            command = json.loads(command_str)
            cmd_type = command.get("type")
            self.logger.debug(f"Received command: {cmd_type}")

            if cmd_type == "validate":
                self.logger.info(f"Received command: {command_str}")
                pw = command["password"]
                success = True
                msg = ""
                if self.password != "":
                    if pw != self.password:
                        success = False
                        msg = "Password is mis-matched"
                response = {
                    "type": "command_response",
                    "success": success,
                    "message": msg
                }
                with self.tcp_lock:
                    self.connected_clients[client_socket].validate = success
                self.send_to_client(client_socket, response)
                return success
            else:
                if not self.connected_clients[client_socket].validate:
                    response = {
                        "type": "command_response",
                        "success": False,
                        "message": "Password should be validated first"
                    }
                    self.send_to_client(client_socket, response)
                    return False
            if cmd_type == "query_version":
                response = {
                    "type": "report_version",
                    "version": version
                }
            elif cmd_type == "start_openocd":
                self.logger.info(f"Received command: {cmd_type}")
                reqId = command['id']
                cfg = json.loads(command['cfg'])
                debugDevice = cfg['device']
                configContent = cfg['cfgfile']
                adapterType = cfg['adapter']
                adapterSpeed = cfg['speed']
                preCommands = ""
                if cfg.get('preCommands', None):
                    preCommands = cfg['preCommands']
                openocdPath = resource_path(os.path.join("xpack-openocd-0.12.0-7-win32-x64", "xpack-openocd-0.12.0-7", "bin", "openocd.exe"))
                configFile = os.path.join(os.getcwd(), f"{debugDevice}.cfg")
                with open(configFile, "w") as f:
                    f.write(configContent)
                if preCommands:
                    args = shlex.split(preCommands)
                    cmd = [openocdPath, *args, "-f", f"{configFile}"]
                else:
                    cmd = [openocdPath,
                        "-c", f"set ADAPTER_TYPE {adapterType}",
                        "-c", f"set ADAPTER_SPEED {adapterSpeed}",
                        "-f", f"{configFile}"]
                # cmd.append("-d3")
                self.logger.info(cmd)
                success = self.start_openocd(cmd, client_socket)

                response = {
                    "type": "command_response",
                    "success": success,
                    "id": reqId
                }
            elif cmd_type == "stop_openocd":
                self.logger.info(f"Received command: {cmd_type}")
                reqId = command['id']
                self.stop_openocd()

                response = {
                    "type": "command_response",
                    "success": True,
                    "id": reqId
                }
            elif cmd_type == "list_com_ports":
                self.logger.debug(f"Received command: {command_str}")
                current_ports = self.scan_com_ports()
                response = {
                    "type": "com_ports_update",
                    "ports": current_ports
                }

            elif cmd_type == "open_port":
                self.logger.info(f"Received command: {command_str}")
                port = command["port"]
                options = command["options"]
                source = command.get("source", "unknown")
                success, msg = self.open_serial_port(
                    port=port,
                    baud_rate=options.get("baudRate", 9600),
                    data_bits=options.get("dataBits", 8),
                    stop_bits=options.get("stopBits", 1),
                    parity=options.get("parity", "none"),
                    client_socket=client_socket,
                    source=source
                )
                response = {"type": "command_response", "port": port, "success": success, "message": msg}
                self.total_bytes = 0
                if success:
                    with self.tcp_lock:
                        self.connected_clients[client_socket].serials.append(port)

            elif cmd_type == "close_port":
                self.logger.info(f"Received command: {command_str}")
                port = command["port"]
                success, msg = self.close_serial_port(port)
                response = {"type": "command_response", "port": port, "success": success, "message": msg}
                self.total_bytes = 0
                if success:
                    with self.tcp_lock:
                        self.connected_clients[client_socket].serials.remove(port)

            elif cmd_type == "baudrate":
                self.logger.info(f"Received command: {command_str}")
                port = command["port"]
                baud = command["baud"]
                success, msg = self.set_baudrate(port, baud)
                response = {"type": "command_response", "port": port, "success": success, "message": msg}

            elif cmd_type == "write_data":
                port = command["port"]
                base64_data = command["data"]

                try:
                    raw_data = base64.b64decode(base64_data, validate=True)
                    data_len = len(raw_data)
                    data_hex = raw_data.hex(' ', 4)
                    self.logger.debug(f"[Serial Write] Port: {port} | Length: {data_len} Bytes | Hex: {data_hex}")
                    # self.logger.debug(f"[Serial Write] Port: {port} | Length: {data_len} Bytes")
                    with self.tcp_lock:
                        success, msg = self.write_serial_data(port, raw_data)
                        response = {
                            "type": "command_response",
                            "port": port,
                            "success": success,
                            "message": msg
                        }
                        self.send_to_client(client_socket, response)

                    self.cur_time = time.time()
                    self.total_bytes += data_len
                    if self.cur_time - self.start_time >= 1.0:
                        self.logger.info(f"[Serial Write] Port: {port} | Speed: {int(self.total_bytes/(self.cur_time - self.start_time))} Bytes/sec")
                        self.start_time = self.cur_time
                        self.total_bytes = 0
                    return True
                except base64.binascii.Error as e:
                    self.logger.error(f"Base64 decode failed: {e}")
                    response = {
                        "type": "command_response", "port": port,
                        "success": False, "message": f"Base64 decode failed: {e}"
                    }

            elif cmd_type == "control_dtr_rts":
                self.logger.info(f"Received command: {command_str}")
                port = command["port"]
                timing = command.get("timing", None)
                action_name = command.get("action_name", "control_dtr_rts")
                success, msg = self.control_dtr_rts(port, timing, action_name)
                response = {"type": "command_response", "port": port, "success": success, "message": msg}

            elif cmd_type == "enter_download_mode":
                self.logger.info(f"Received command: {command_str}")
                port = command["port"]
                timing = command.get("timing", None)
                success, msg = self.enter_download_mode(port, timing)
                response = {"type": "command_response", "port": port, "success": success, "message": msg}

            elif cmd_type == "reset_device":
                self.logger.info(f"Received command: {command_str}")
                port = command["port"]
                timing = command.get("timing", None)
                success, msg = self.reset_device(port, timing)
                response = {"type": "command_response", "port": port, "success": success, "message": msg}

            else:
                raise ValueError(f"Unknown command type: {cmd_type}")

            if response:
                self.send_to_client(client_socket, response)

        except json.JSONDecodeError:
            self.logger.error(f"Command JSON parsing failed: {command_str}")
            error_response = {"type": "command_response", "success": False, "message": f"Command JSON parsing failed", "port": ""}
            self.send_to_client(client_socket, error_response)
        except Exception as e:
            self.logger.error(f"Error occurred while processing the command: {command_str}", exc_info=True)
            port_in_cmd = command.get("port", "") if 'command' in locals() else ""
            error_response = {"type": "command_response", "success": False, "message": f"Command processing error: {e}", "port": port_in_cmd}
            self.send_to_client(client_socket, error_response)
        return True

    # --- Serial port ---
    def scan_com_ports(self) -> List[str]:
        ports = []
        try:
            for port in serial.tools.list_ports.comports():
                if port.device:
                    ports.append([port.device, port.description])
                # self.logger.info(f'{port.device}, {port.name}, {port.description}')
        except Exception as e:
            self.logger.error("Error occurred while scanning COM ports", exc_info=True)
        return sorted(ports)

    def open_serial_port(self, port: str, baud_rate: int, data_bits: int, stop_bits: int, parity: str, client_socket, source: str = "unknown") -> tuple[bool, str]:
        # Phase 1: check if preemption is needed (serial_lock only)
        need_preempt = False
        monitor_socket = None
        with self.serial_lock:
            if port in self.open_serials:
                owner = self.port_owners.get(port, {})
                owner_source = owner.get("source", "unknown")
                if source == "flash" and owner_source == "monitor":
                    need_preempt = True
                    monitor_socket = owner.get("client_socket")
                else:
                    self.logger.warning(f"Attempted to open an already opened serial port {port} (owner: {owner_source}, requester: {source})")
                    return False if (source == "monitor" and owner_source == "flash") else True, \
                        "Serial port occupied by flash" if (source == "monitor" and owner_source == "flash") else "Serial port already opened"

        # Phase 2: preempt monitor (outside serial_lock to avoid deadlock)
        if need_preempt:
            self.logger.info(f"Flash preempts monitor on port {port}, closing monitor connection")
            if monitor_socket:
                self.send_to_client(monitor_socket, {"type": "port_preempted", "port": port, "message": "Port preempted by flash"})
                with self.tcp_lock:
                    if monitor_socket in self.connected_clients:
                        try:
                            self.connected_clients[monitor_socket].serials.remove(port)
                        except ValueError:
                            pass
            self.close_serial_port(port)

        # Phase 3: open the port (serial_lock again)
        with self.serial_lock:
            if port in self.open_serials:
                return True, "Serial port already opened"
            try:
                parity_map = {"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN, "odd": serial.PARITY_ODD}
                stop_bits_map = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}

                self.logger.info(f"Opening serial port {port} (Baud: {baud_rate}, Config: {data_bits}{parity[0].upper()}{stop_bits})...")

                ser = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    bytesize=data_bits,
                    parity=parity_map.get(parity, serial.PARITY_NONE),
                    stopbits=stop_bits_map.get(stop_bits, serial.STOPBITS_ONE)
                )

                if ser.is_open:
                    self.open_serials[port] = ser
                    self.port_owners[port] = {"source": source, "client_socket": client_socket}
                    threading.Thread(target=self.listen_serial_data, args=(port, ser, client_socket), daemon=True).start()
                    self.logger.info(f"Serial port {port} opened successfully (source: {source}).")
                    return True, "Serial port opened successfully"
                else:
                    self.logger.error(f"Serial port {port} failed to open (unknown error).")
                    return False, "Failed to open serial port (unknown error)"
            except Exception as e:
                self.logger.error(f"Failed to open serial port {port}: {e}", exc_info=False)
                return False, f"Open failed: {e}"

    def close_serial_port(self, port: str) -> tuple[bool, str]:
        with self.serial_lock:
            if port not in self.open_serials:
                self.logger.warning(f"Attempted to close a serial port that is not open or already closed {port}")
                return True, "Serial port closed or not opened"
            try:
                ser = self.open_serials.pop(port)
                self.port_owners.pop(port, None)
                if ser.is_open:
                    ser.close()
                self.logger.info(f"Serial port {port} closed successfully.")
                return True, "Serial port closed successfully"
            except Exception as e:
                self.logger.error(f"Error occurred while closing serial port {port}", exc_info=True)
                return False, f"Close failed: {e}"

    def write_serial_data(self, port: str, data: bytes) -> tuple[bool, str]:
        with self.serial_lock:
            if port not in self.open_serials:
                self.logger.error(f"Write failed: Serial port {port} is not opened.")
                return False, "Serial port not opened"
            try:
                ser = self.open_serials[port]
                ser.write(data)
                return True, f"Binary data sent successfully (length: {len(data)} bytes)"
            except Exception as e:
                self.logger.error(f"Error occurred while writing to serial port {port}", exc_info=True)
                return False, f"Send failed: {e}"

    def set_baudrate(self, port: str, baud: int) -> tuple[bool, str]:
        """Set baudrate without closing the serial port (preserves DTR/RTS states)"""
        with self.serial_lock:
            if port not in self.open_serials:
                self.logger.error(f"baudrate failed: Serial port {port} is not opened.")
                return False, "Serial port not opened"
            try:
                ser = self.open_serials[port]
                ser.baudrate = baud
                return True, f"baudrate successfully set to {baud}"
            except Exception as e:
                self.logger.error(f"Error setting baudrate on {port}: {e}")
                return False, f"Set baudrate failed: {e}"

    def control_dtr_rts(self, port: str, timing: list = None, action_name: str = "control_dtr_rts") -> tuple[bool, str]:
        """
        Execute DTR/RTS timing sequence to control device.

        This is a generic API for controlling DTR/RTS signals with custom timing sequences.
        Common use cases include entering download mode, resetting device, etc.

        :param port: Serial port name (e.g., "COM3", "/dev/ttyUSB0")
        :param timing: List of timing steps. Each step is a dict with one of:
                       - {"dtr": 0|1} - Set DTR signal (0=False, 1=True)
                       - {"rts": 0|1} - Set RTS signal (0=False, 1=True)
                       - {"delay": ms} - Delay in milliseconds
                       If None, no operation is performed.
        :param action_name: Description of the action for logging (e.g., "enter_download_mode", "reset_device")
        :return: (success, message) tuple
        """
        with self.serial_lock:
            if port not in self.open_serials:
                return False, "Serial port not opened"

            if timing is None:
                return True, "No timing specified, no operation performed"

            try:
                ser = self.open_serials[port]

                # Save original states
                dtr_orig = ser.dtr
                rts_orig = ser.rts

                # Execute timing sequence
                for item in timing:
                    for key, val in item.items():
                        if key.upper() == "DTR":
                            ser.dtr = (val != 0)
                            self.logger.debug(f"Set DTR = {val != 0}")
                        elif key.upper() == "RTS":
                            ser.rts = (val != 0)
                            self.logger.debug(f"Set RTS = {val != 0}")
                        elif key.upper() == "DELAY":
                            time.sleep(val / 1000)
                            self.logger.debug(f"Delay {val}ms")

                # Restore original states
                ser.dtr = dtr_orig
                ser.rts = rts_orig

                self.logger.info(f"{action_name} completed on {port}")
                return True, f"{action_name} successfully"
            except Exception as e:
                self.logger.error(f"Error during {action_name} on {port}: {e}")
                return False, f"{action_name} failed: {e}"

    def enter_download_mode(self, port: str, timing: list = None) -> tuple[bool, str]:
        """
        Execute DTR/RTS sequence to enter download mode.
        Uses default timing from Reburn.cfg if not specified.
        """
        if timing is None:
            timing = [
                {"dtr": 0}, {"rts": 1}, {"delay": 200},
                {"dtr": 1}, {"rts": 0}, {"delay": 100},
                {"dtr": 0}
            ]
        return self.control_dtr_rts(port, timing, "enter_download_mode")

    def reset_device(self, port: str, timing: list = None) -> tuple[bool, str]:
        """
        Execute DTR/RTS sequence to reset device.
        Uses default timing from Reset.cfg if not specified.
        """
        if timing is None:
            timing = [
                {"dtr": 0}, {"rts": 1}, {"delay": 200},
                {"rts": 0}, {"dtr": 0}
            ]
        return self.control_dtr_rts(port, timing, "reset_device")

    def listen_serial_data(self, port: str, ser: serial.Serial, client_socket):
        while self.running and port in self.open_serials and ser.is_open:
            try:
                #rlist, _, _ = select.select([ser], [], [], 0.001)
                #if rlist:
                #    raw_data = ser.read(ser.in_waiting)
                raw_data = ser.read(1)
                if not raw_data:
                    continue
                raw_data += ser.read(ser.in_waiting)
                base64_data = base64.b64encode(raw_data).decode('utf-8')
                self.logger.debug(f"[Serial Receive] Port: {port} | Raw Length: {len(raw_data)} | Hex: {raw_data.hex(' ')}")

                message = {
                    "type": "serial_data",
                    "port": port,
                    "data": base64_data
                }
                with self.tcp_lock:
                    self.send_to_client(client_socket, message)

                self.logger.debug(f"[Serial Receive] tcp send complete")
            except Exception as e:
                # If the serial port is pulled out, an exception will be thrown here
                self.logger.error(f"Exception occurred while listening to serial port {port}, listening stopped.")
                self.close_serial_port(port)
                break

    def send_to_client(self, client_socket: socket.socket, message: dict):
        if not self.running or client_socket not in self.connected_clients:
            return
        try:
            message_str = json.dumps(message) + "\n"
            #self.logger.error(f"Serial port sent tcp length:{len(message_str)}")
            client_socket.sendall(message_str.encode('utf-8'))
        except Exception as e:
            self.logger.error(f"Error occurred while sending message to client", exc_info=True)

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)

class MsFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
        ms = int(record.msecs)
        return "%s.%03d" % (t, ms)

def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')

class MainApp(tk.Tk):
    def __init__(self, server, log_queue):
        super().__init__()
        self.server = server
        self.log_queue = log_queue
        self.tray_icon = None
        self.save_log_file = None
        self.is_quitting = False

        self.withdraw()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        try:
            icon_path = resource_path("realtek.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
            else:
                print(f"Warning: Icon not found at {icon_path}")
        except Exception as e:
            print(f"Failed to load icon: {e}")

        self._init_ui()
        self._init_menu()
        center_window(self, 800, 500)
        # self.deiconify()
        self.check_log_queue()
        threading.Thread(target=self.monitor_ip_change, daemon=True).start()

    def _init_ui(self):
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)
        self.log_edit = scrolledtext.ScrolledText(self, state='disabled', font=('Consolas', 10))
        # self.log_edit.pack(expand=True, fill='both', padx=5, pady=(5, 0))
        self.log_edit.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 5))
        self._create_statusbar()

    def _init_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Log As... (Ctrl+S)", command=self.save_logs)
        file_menu.add_command(label="Clear Log (Ctrl+L)", command=self.clear_log)

    def _create_statusbar(self):
        statusbar_frame = tk.Frame(self, bg="#e4e7ed", relief="sunken", bd=1)
        # statusbar_frame.pack(side="bottom", fill="x", after=self.log_edit)
        statusbar_frame.grid(row=1, column=0, sticky="ew", pady=0)
        # statusbar_frame.place(x=0, rely=1.0, anchor="sw", relwidth=1.0, height=25)

        self.label_ip = tk.Label(
            statusbar_frame,
            text="🌐 IP: Loading...",
            bg="#e4e7ed",
            fg="#606266",
            font=("Segoe UI", 9),
            anchor="w",
            padx=9,
            pady=3
        )
        self.label_ip.pack(side="left", fill="x", expand=True)
        ethernet_ip, wifi_ip = self._get_ips_windows()
        self._update_ip_label(ethernet_ip, wifi_ip)

        separator = tk.Frame(statusbar_frame, bg="#d3d3d3", width=1)
        separator.pack(side="left", fill="y", padx=5, pady=2)

        self.label_version = tk.Label(
            statusbar_frame,
            text=f"{APP_VERSION}",
            bg="#e4e7ed",
            fg="#1D1D1F",
            font=("Segoe UI", 9),
            anchor="e",
            padx=9,
            pady=3
        )
        self.label_version.pack(side="right")

    def check_log_queue(self):
        max_batch = 100
        batch_data = []

        try:
            while len(batch_data) < max_batch:
                batch_data.append(self.log_queue.get_nowait())
        except queue.Empty:
            pass

        if batch_data:
            combined_text = "\n".join(batch_data) + "\n"
            self.append_log(combined_text)

        if not self.is_quitting:
            interval = 10 if len(batch_data) >= max_batch else 100
            self.after(interval, self.check_log_queue)

    def append_log(self, text):
        try:
            self.log_edit.config(state='normal')
            self.log_edit.insert(tk.END, text)
            self.log_edit.see(tk.END)
            self.log_edit.config(state='disabled')
            if self.save_log_file:
                self.save_log_file.write(text)
                self.save_log_file.flush()
        except Exception as e:
            print(f"Error appending log: {e}")

    def save_logs(self):
        default_filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = filedialog.asksaveasfilename(
            initialfile=default_filename,
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            self.save_log_file = open(file_path, 'w', encoding='utf-8')

    def clear_log(self):
        self.log_edit.config(state='normal')
        self.log_edit.delete(1.0, tk.END)
        self.log_edit.config(state='disabled')

    def hide_window(self):
        self.withdraw()
        if self.tray_icon:
            self.after(10, lambda: self.tray_icon.notify(
                "The program has been minimized to the system tray.", 
                f"{APP_NAME} {APP_VERSION}"
            ))

    def show_window(self):
        self.deiconify()
        self.lift()

    def quit_app(self):
        self.is_quitting = True
        try:
            self.server.stop_server()
        except Exception as e:
            print(f"Error stopping server during quit: {e}")

        if self.save_log_file:
            try:
                self.save_log_file.close()
            except IOError as e:
                print(f"Error closing log file: {e}")

        if self.tray_icon:
            threading.Thread(target=self._stop_tray_nowait, daemon=True).start()

        try:
            self.quit()
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    def _stop_tray_nowait(self):
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except: pass

    def _update_ip_label(self, ethernet_ip, wifi_ip):
        if self.winfo_exists():
            self.label_ip.config(text=f"🌐 Ethernet IP: {ethernet_ip} | WLAN IP: {wifi_ip}")

    def _get_ips_windows(self):
        ethernet_ip = "N/A"
        wifi_ip = "N/A"

        try:
            result = subprocess.check_output(
                "ipconfig",
                shell=True,
                text=True,
                encoding='gbk',
                timeout=5
            )

            adapters = re.split(r'\n(?=\S)', result)

            for adapter in adapters:

                if not adapter.strip():
                    continue

                is_ethernet = bool(re.search(
                    r'以太网适配器|ethernet adapter',
                    adapter,
                    re.IGNORECASE
                ))

                is_wifi = bool(re.search(
                    r'无线局域网适配器|wireless lan adapter|wi-fi',
                    adapter,
                    re.IGNORECASE
                ))

                ipv4_match = re.search(
                    r'(?:IPv4 地址|IPv4 Address)[^\d]*([\d.]+)',
                    adapter,
                    re.IGNORECASE
                )

                if ipv4_match:
                    ip = ipv4_match.group(1)

                    if is_ethernet and ethernet_ip == "N/A":
                        ethernet_ip = ip
                    elif is_wifi and wifi_ip == "N/A":
                        wifi_ip = ip

        except subprocess.TimeoutExpired:
            print("ipconfig timeout")
        except Exception as e:
            print(f"Windows IP fetch error: {e}")

        return ethernet_ip, wifi_ip

    def get_local_ip_list(self):
        ip_list = []
        try:
            hostname = socket.gethostname()
            addrs = socket.getaddrinfo(hostname, None)
            for item in addrs:
                if ':' not in item[4][0]:
                    ip_list.append(item[4][0])
        except Exception as e:
            print(f"Error getting local IP: {e}")
        ip_list.sort()
        return ip_list

    def diff_ip_lists(self, last_ips, current_ips):
        last_ips_set = set(last_ips)
        current_ips_set = set(current_ips)
        added = current_ips_set - last_ips_set
        removed = last_ips_set - current_ips_set

        info_lines = [f"{APP_NAME} IP changed!"]
        info_lines.append(f"Old IP: {last_ips}")
        info_lines.append(f"New IP: {current_ips}")
        if added:
            for ip in added:
                info_lines.append(f"Added IP:  + {ip}")
        if removed:
            for ip in removed:
                info_lines.append(f"Removed IP:  - {ip}")
        return added, removed, "\n".join(info_lines)

    def monitor_ip_change(self):
        last_ips = self.get_local_ip_list()
        while not self.is_quitting:
            time.sleep(3)
            current_ips = self.get_local_ip_list()
            ethernet_ip, wifi_ip = self._get_ips_windows()
            if current_ips != last_ips:
                self.after(0, lambda: self._update_ip_label(ethernet_ip, wifi_ip))
                added, removed, msg = self.diff_ip_lists(last_ips, current_ips)
                try:
                    if added or removed:
                        self.tray_icon.notify(msg, "Network Change")
                except: pass
                last_ips = current_ips.copy()

class LoginDialog(tk.Toplevel):
    def __init__(self, parent, default_pwd, default_level):
        super().__init__(parent)
        self.parent = parent
        self.login_result = None
        self.default_pwd = default_pwd
        self.default_level = default_level

        self.withdraw()

        self.title(f'{APP_NAME} Login')
        self.resizable(False, False)
        center_window(self, 400, 350)
        self._init_ui()

        self.grab_set()
        self.focus_set()
        self.attributes("-topmost", True)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.deiconify()

        self._load_ip_addresses()

    def _init_ui(self):
        self.configure(bg="#f5f7fa")

        tk.Label(self, text=f"{APP_NAME} Login Config",
                 font=("Segoe UI", 14, "bold"), bg="#f5f7fa", fg="#303133").pack(pady=(20, 10))

        group = tk.LabelFrame(self, text="PARAMETERS", bg="white", fg="#909399",
                              font=("Segoe UI", 10, "bold"), padx=20, pady=20)
        group.pack(fill="x", padx=30, pady=0)

        frame_form = tk.Frame(group, bg="white")
        frame_form.pack(fill="x")

        tk.Label(frame_form, text="Set Password:", bg="white").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_pwd = ttk.Entry(frame_form, width=25)
        self.entry_pwd.grid(row=0, column=1, sticky="e", pady=5, padx=10)
        self.entry_pwd.insert(0, self.default_pwd)

        tk.Label(frame_form, text="Set Log Level:", bg="white").grid(row=1, column=0, sticky="w", pady=5)
        self.combo_level = ttk.Combobox(frame_form, values=list(log_levels.keys()), state="readonly", width=23)
        if self.default_level in log_levels.keys():
            self.combo_level.set(self.default_level)
        else:
            self.combo_level.current(1)
        self.combo_level.grid(row=1, column=1, sticky="e", pady=5, padx=10)

        tk.Label(frame_form, text="Ethernet IPv4 Address:", bg="white").grid(row=2, column=0, sticky="w", pady=5)
        self.label_ethernet_ip = tk.Label(
            frame_form,
            text="🔍 Loading...",
            bg="white",
            fg="#909399",
            font=("Consolas", 10),
            cursor="hand2"
        )
        self.label_ethernet_ip.grid(row=2, column=1, sticky="e", pady=5, padx=10)
        self.label_ethernet_ip.bind("<Button-1>", lambda e: self._copy_to_clipboard(self.ethernet_ip))

        tk.Label(frame_form, text="WLAN IPv4 Address:", bg="white").grid(row=3, column=0, sticky="w", pady=5)
        self.label_wifi_ip = tk.Label(
            frame_form,
            text="🔍 Loading...",
            bg="white",
            fg="#909399",
            font=("Consolas", 10),
            cursor="hand2"
        )
        self.label_wifi_ip.grid(row=3, column=1, sticky="e", pady=5, padx=10)
        self.label_wifi_ip.bind("<Button-1>", lambda e: self._copy_to_clipboard(self.wifi_ip))

        frame_form.columnconfigure(1, weight=1)

        btn_login = tk.Button(self, text="Confirm and Login", bg="#409eff", fg="white",
                              font=("Segoe UI", 10, "bold"), relief="flat",
                              command=self.handle_login)
        btn_login.pack(pady=20, ipadx=10, ipady=5)

        self._create_statusbar()

    def _load_ip_addresses(self):
        ethernet_ip, wifi_ip = self.parent._get_ips_windows()
        self.ethernet_ip = ethernet_ip
        self.wifi_ip = wifi_ip
        if ethernet_ip and ethernet_ip != "N/A":
            self.label_ethernet_ip.config(text=ethernet_ip, fg="#039B03")
        else:
            self.label_ethernet_ip.config(text="Not Connected", fg="#f11010")

        if wifi_ip and wifi_ip != "N/A":
            self.label_wifi_ip.config(text=wifi_ip, fg="#039B03")
        else:
            self.label_wifi_ip.config(text="Not Connected", fg="#f11010")

    def _copy_to_clipboard(self, ip_address):
        if ip_address and ip_address != "N/A" and ip_address != "Not Connected":
            try:
                self.clipboard_clear()
                self.clipboard_append(ip_address)
                self.update()
                self._show_copy_feedback()
            except Exception as e:
                print(f"Copy error: {e}")

    def _show_copy_feedback(self):
        feedback = tk.Label(
            self,
            text="✅ IP Copied to Clipboard!",
            bg="#67c23a",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5
        )
        feedback.place(relx=0.5, rely=0.9, anchor="center")

        self.after(1500, feedback.destroy)

    def _create_statusbar(self):
        statusbar_frame = tk.Frame(self, bg="#e4e7ed", relief="sunken", bd=1)
        statusbar_frame.pack(side="bottom", fill="x")
        statusbar_frame.place(x=0, rely=1.0, anchor="sw", relwidth=1.0, height=25)

        separator = tk.Frame(statusbar_frame, bg="#d3d3d3", width=1)
        separator.pack(side="left", fill="y", padx=5, pady=2)

        self.label_user = tk.Label(
            statusbar_frame,
            text=f"{APP_VERSION}",
            bg="#e4e7ed",
            fg="#606266",
            font=("Segoe UI", 9),
            anchor="e",
            padx=10,
            pady=8
        )
        self.label_user.pack(side="right")

    def handle_login(self):
        self.login_result = (self.entry_pwd.get().strip(), self.combo_level.get())
        self.destroy()

    def on_close(self):
        self.login_result = None
        self.destroy()

class SelectionDialog(simpledialog.Dialog):
    def __init__(self, parent, title, prompt, options, initial_value=None):
        self.prompt = prompt
        self.options = options
        self.initial_value = initial_value
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        tk.Label(master, text=self.prompt).pack(pady=(10, 5))

        self.combo = ttk.Combobox(master, values=self.options, state="readonly")
        if self.initial_value and self.initial_value in self.options:
            self.combo.set(self.initial_value)
        elif self.options:
            self.combo.current(0)
        self.combo.pack(padx=20, pady=5)

        return self.combo

    def apply(self):
        self.result = self.combo.get()

class TrayHandler:
    def __init__(self, main_app, server, icon_path):
        self.main_app = main_app
        self.server = server
        self.icon_path = icon_path
        self.systray = None

    def setup_tray(self):
        # Use consistent label - actual state is checked when clicked
        menu_options = (
            ("Show Main Window", None, self.on_show),
            ("Set Password", None, self.set_password),
            ("Set Log Level", None, self.set_log_level),
            ("Toggle Auto Start", None, self.toggle_autostart),
        )

        try:
            self.systray = SysTrayIcon(
                self.icon_path,
                f"{APP_NAME} {APP_VERSION}",
                menu_options,
                on_quit=self.on_exit
            )
            self.systray.start()
        except Exception as e:
            print(f"Tray Error: {e}")

    def show_toast(self, root, message, timeout=8000):
        try:
            toast = tk.Toplevel(root)
            toast.overrideredirect(True)

            toast.attributes("-topmost", True)

            label = tk.Label(toast, text=message, bg="#333333", fg="white", 
                            padx=20, pady=10, font=("Arial", 12),
                            justify='left',
                            anchor='w')
            label.pack(fill='both', expand=True)

            root.update_idletasks()
            width = label.winfo_reqwidth()
            height = label.winfo_reqheight()

            try:
                root_x = root.winfo_x()
                root_y = root.winfo_y()
                root_w = root.winfo_width()
                root_h = root.winfo_height()
                if root.state() == 'withdrawn' or root_x < 0:
                    raise ValueError("Main window hidden")

                x = root_x + (root_w // 2) - (width // 2)
                y = root_y + (root_h // 2) - (height // 2)
            except:
                screen_w = root.winfo_screenwidth()
                screen_h = root.winfo_screenheight()
                x = (screen_w // 2) - (width // 2)
                y = (screen_h // 2) - (height // 2)

            toast.geometry(f"+{x}+{y}")
            toast.after(timeout, toast.destroy)
        except Exception as e:
            print(f"Error showing toast: {e}")

    def notify(self, message, title):
        print(f"--- [TRAY NOTIFY] {title}: {message} ---")
        if title == "Network Change":
            self.main_app.after(0, lambda: self.show_toast(self.main_app, message))

    def stop(self):
        if self.systray:
            self.systray.shutdown()

    def on_show(self, systray):
        self.main_app.after(0, self.main_app.show_window)

    def on_exit(self, systray):
        self.main_app.after(0, self.main_app.quit_app)

    def set_password(self, systray):
        self.main_app.after(0, self._pwd_dialog)

    def _pwd_dialog(self):
        current_pwd = self.server.password if self.server.password else ""
        pwd = simpledialog.askstring("Set Password", "Input new password:", initialvalue=current_pwd, parent=self.main_app)
        if pwd is not None:
            if self.server.password != pwd:
                level_name = self.server.getLevelName(self.server.logger.level)
                save_config(pwd, level_name)
                messagebox.showinfo("Success", "Password set! Server restarting...", parent=self.main_app)
                threading.Thread(target=self._restart_server_thread, args=(pwd,), daemon=True).start()
            else:
                messagebox.showinfo("Success", "Password unchanged.", parent=self.main_app)

    def _restart_server_thread(self, new_pwd):
        self.server.stop_server()
        time.sleep(1.0)
        self.server.password = new_pwd
        self.server.start_server(self.main_app)

    def set_log_level(self, systray):
        self.main_app.after(0, self._level_dialog)

    def _level_dialog(self):
        current_level_name = "INFO" 
        for name, level in log_levels.items():
            if self.server.logger.level == level:
                current_level_name = name
                break

        dialog = SelectionDialog(
            self.main_app, 
            "Set Log Level", 
            "Select Log Level:", 
            list(log_levels.keys()), 
            initial_value=current_level_name
        )

        level = dialog.result
        if level:
            self.server.logger.setLevel(log_levels[level])
            save_config(self.server.password, level)
            messagebox.showinfo("Success", f"Level set to {level}", parent=self.main_app)

    def toggle_autostart(self, systray):
        self.main_app.after(0, self._toggle_autostart_dialog)

    def _toggle_autostart_dialog(self):
        current_state = is_autostart_enabled()
        success = False
        if current_state:
            # Currently enabled, disable it
            success = disable_autostart()
            msg = "Auto-start disabled. The application will not start on Windows login."
        else:
            # Currently disabled, enable it
            success = enable_autostart()
            msg = "Auto-start enabled. The application will start minimized to tray on Windows login."

        if success:
            messagebox.showinfo("Success", msg, parent=self.main_app)
        else:
            messagebox.showerror("Error", "Failed to change auto-start settings.", parent=self.main_app)

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument('--minimized', '-m', action='store_true',
                       help='Start minimized to system tray (for auto-start)')
    args, unknown_args = parser.parse_known_args()

    # if sys.platform == "win32":
    #     if not ctypes.windll.shell32.IsUserAnAdmin():
    #         # print("Administrator privileges are required to set the firewall, attempting to restart as administrator...")
    #         try:
    #             ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    #         except Exception as e:
    #             print(f"Automatic elevation failed: {e}")
    #             print("Please manually run this script as administrator.")
    #             # input("Press Enter to exit.")
    #         sys.exit(0)

    server = AmebaSerialServer()
    # if sys.platform == "win32":
    #     server.logger.info("Administrator privileges obtained.")
    #     threading.Thread(target=server.setup_firewall, daemon=True).start()

    log_queue = queue.Queue()
    handler = QueueHandler(log_queue)
    handler.setFormatter(MsFormatter("%(asctime)s [%(levelname)s]: %(message)s"))
    server.logger.addHandler(handler)

    last_config = load_config()
    saved_pwd = last_config.get("password", "")
    saved_level = last_config.get("log_level", "INFO")

    main_app = MainApp(server, log_queue)
    main_app.update_idletasks()

    # If running minimized (autostart), skip login dialog and use saved config
    if args.minimized:
        pwd = saved_pwd
        level = saved_level
        print(f"Auto-start: using saved password, log level: {level}")
    else:
        login_dialog = LoginDialog(main_app, default_pwd=saved_pwd, default_level=saved_level)
        main_app.wait_window(login_dialog)

        if not login_dialog.login_result:
            print("Login cancelled. Exiting.")
            main_app.destroy()
            sys.exit(0)

        pwd, level = login_dialog.login_result
        print(f"Login Success: {pwd}, {level}")
        save_config(pwd, level)

    server.password = pwd
    server.logger.setLevel(log_levels[level])

    tray = TrayHandler(main_app, server, resource_path("realtek.ico"))
    main_app.tray_icon = tray
    tray.setup_tray()

    server.logger.info("The server is running...")
    threading.Thread(target=server.start_server, args=(main_app,), daemon=True).start()

    # If minimized (autostart), hide window to tray; otherwise show window
    if args.minimized:
        main_app.withdraw()
    else:
        main_app.show_window()
    try:
        main_app.mainloop()
    except KeyboardInterrupt:
        main_app.quit_app()

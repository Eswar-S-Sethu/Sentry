"""
System Monitor Module
Track NUC hardware stats: CPU, RAM, temperature, disk, network
"""

import psutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_cpu_temperature():
    """Get CPU temperature"""
    try:
        # Try reading from thermal zone (works on most Linux systems)
        temps = psutil.sensors_temperatures()

        if 'coretemp' in temps:
            # Intel CPU temperature
            core_temps = [temp.current for temp in temps['coretemp']]
            return sum(core_temps) / len(core_temps)
        elif 'cpu_thermal' in temps:
            # Generic CPU thermal
            return temps['cpu_thermal'][0].current
        elif temps:
            # Get first available temperature sensor
            first_sensor = list(temps.keys())[0]
            return temps[first_sensor][0].current
        else:
            return None
    except Exception as e:
        logger.debug(f"Could not read temperature: {e}")
        return None


def get_system_stats():
    """Get comprehensive system statistics"""
    try:
        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        # Memory
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Disk
        disk = psutil.disk_usage('/')

        # Network
        net_io = psutil.net_io_counters()

        # Temperature
        cpu_temp = get_cpu_temperature()

        # System uptime
        boot_time = psutil.boot_time()
        uptime_seconds = datetime.now().timestamp() - boot_time
        uptime_hours = uptime_seconds / 3600
        uptime_days = uptime_hours / 24

        # Process count
        process_count = len(psutil.pids())

        stats = {
            'cpu': {
                'usage_percent': cpu_percent,
                'count': cpu_count,
                'frequency_mhz': cpu_freq.current if cpu_freq else None,
                'temperature_c': cpu_temp
            },
            'memory': {
                'total_gb': memory.total / (1024 ** 3),
                'used_gb': memory.used / (1024 ** 3),
                'available_gb': memory.available / (1024 ** 3),
                'usage_percent': memory.percent
            },
            'swap': {
                'total_gb': swap.total / (1024 ** 3),
                'used_gb': swap.used / (1024 ** 3),
                'usage_percent': swap.percent
            },
            'disk': {
                'total_gb': disk.total / (1024 ** 3),
                'used_gb': disk.used / (1024 ** 3),
                'free_gb': disk.free / (1024 ** 3),
                'usage_percent': disk.percent
            },
            'network': {
                'bytes_sent_gb': net_io.bytes_sent / (1024 ** 3),
                'bytes_recv_gb': net_io.bytes_recv / (1024 ** 3),
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            },
            'system': {
                'uptime_days': uptime_days,
                'uptime_hours': uptime_hours,
                'process_count': process_count
            }
        }

        return stats

    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return None


def format_system_stats(stats):
    """Format system stats into a readable message"""
    if not stats:
        return "❌ Could not retrieve system stats"

    message = "🖥️ *NUC System Status*\n\n"

    # CPU
    cpu = stats['cpu']
    cpu_bar = "█" * int(cpu['usage_percent'] / 5)  # 20 bars max
    message += f"*CPU ({cpu['count']} cores)*\n"
    message += f"Usage: {cpu['usage_percent']:.1f}% {cpu_bar}\n"
    if cpu['frequency_mhz']:
        message += f"Frequency: {cpu['frequency_mhz']:.0f} MHz\n"
    if cpu['temperature_c']:
        temp_emoji = "🔥" if cpu['temperature_c'] > 70 else "🌡️"
        message += f"Temperature: {cpu['temperature_c']:.1f}°C {temp_emoji}\n"
    message += "\n"

    # Memory
    mem = stats['memory']
    mem_bar = "█" * int(mem['usage_percent'] / 5)
    message += "*Memory (RAM)*\n"
    message += f"Usage: {mem['used_gb']:.1f}GB / {mem['total_gb']:.1f}GB ({mem['usage_percent']:.1f}%)\n"
    message += f"{mem_bar}\n"
    message += f"Available: {mem['available_gb']:.1f}GB\n"
    message += "\n"

    # Disk
    disk = stats['disk']
    disk_bar = "█" * int(disk['usage_percent'] / 5)
    message += "*Disk (SSD)*\n"
    message += f"Usage: {disk['used_gb']:.1f}GB / {disk['total_gb']:.1f}GB ({disk['usage_percent']:.1f}%)\n"
    message += f"{disk_bar}\n"
    message += f"Free: {disk['free_gb']:.1f}GB\n"
    message += "\n"

    # Network
    net = stats['network']
    message += "*Network*\n"
    message += f"Sent: {net['bytes_sent_gb']:.2f}GB ({net['packets_sent']:,} packets)\n"
    message += f"Received: {net['bytes_recv_gb']:.2f}GB ({net['packets_recv']:,} packets)\n"
    message += "\n"

    # System
    sys = stats['system']
    if sys['uptime_days'] >= 1:
        uptime_str = f"{sys['uptime_days']:.1f} days"
    else:
        uptime_str = f"{sys['uptime_hours']:.1f} hours"
    message += "*System*\n"
    message += f"Uptime: {uptime_str}\n"
    message += f"Processes: {sys['process_count']}\n"

    return message


def get_quick_stats():
    """Get quick one-line system stats"""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent
        temp = get_cpu_temperature()

        temp_str = f"{temp:.0f}°C" if temp else "N/A"
        return f"CPU: {cpu:.0f}% | RAM: {mem:.0f}% | Temp: {temp_str}"
    except Exception as e:
        logger.error(f"Error getting quick stats: {e}")
        return "Stats unavailable"
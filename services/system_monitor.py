import psutil


def get_system_metrics():
    """
    Récupère les principales informations système utilisées par NEXCORE.
    """

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    frequency = psutil.cpu_freq()

    return {
        "cpu": cpu,
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_frequency": frequency.current if frequency else None,

        "ram_percent": ram.percent,
        "ram_used": ram.used,
        "ram_total": ram.total,

        "disk_percent": disk.percent,
        "disk_free": disk.free,
        "disk_total": disk.total,
    }
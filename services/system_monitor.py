import psutil


def get_system_metrics():
    """
    Récupère les principales informations système utilisées par NEXCORE.
    """

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")

    return {
    "cpu": cpu,

    "ram_percent": ram.percent,
    "ram_used": ram.used,
    "ram_total": ram.total,

    "disk_percent": disk.percent,
    "disk_free": disk.free,
    "disk_total": disk.total,
}
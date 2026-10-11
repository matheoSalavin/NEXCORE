import psutil

from PySide6.QtCore import QThread, Signal


class ProcessWorker(QThread):
    """
    Récupère les informations sur les processus Windows dans
    un thread séparé pour éviter de bloquer l'interface.
    """

    results_ready = Signal(list)
    error_occurred = Signal(str)

    def run(self):
        """Récupère le nom, le PID, le CPU et la RAM des processus."""
        try:
            processes = []

            for proc in psutil.process_iter(
                ["pid", "name", "memory_info", "cpu_percent"]
            ):
                try:
                    info = proc.info

                    if not info["name"]:
                        continue

                    memory = info["memory_info"]
                    ram_mb = memory.rss / (1024 ** 2) if memory else 0
                    cpu = info["cpu_percent"] or 0

                    processes.append(
                        (info["name"], info["pid"], cpu, ram_mb)
                    )

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue

            processes.sort(key=lambda item: item[3], reverse=True)
            self.results_ready.emit(processes)

        except Exception as error:
            self.error_occurred.emit(str(error))


def terminate_process(pid, expected_name):
    """
    Tente de terminer un processus après avoir vérifié son identité.
    """

    try:
        process = psutil.Process(pid)

        # Vérifie que le PID appartient toujours au processus attendu.
        if process.name() != expected_name:
            return "changed"

        process.terminate()

        try:
            process.wait(timeout=3)
        except psutil.TimeoutExpired:
            return "timeout"

        return "success"

    except psutil.NoSuchProcess:
        return "not_found"

    except psutil.AccessDenied:
        return "access_denied"

    except Exception as error:
        return f"error:{error}"
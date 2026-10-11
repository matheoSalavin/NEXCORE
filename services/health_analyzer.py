def analyze_system(metrics):
    """
    Analyse l'état du PC et retourne un score sur 100
    ainsi qu'une liste de diagnostics.
    """

    score = 100
    diagnostics = []

    cpu = metrics["cpu"]
    ram = metrics["ram_percent"]
    disk = metrics["disk_percent"]

    # Analyse du processeur
    if cpu >= 90:
        score -= 25
        diagnostics.append(("danger", "Processeur fortement sollicité"))
    elif cpu >= 70:
        score -= 10
        diagnostics.append(("warning", "Utilisation CPU élevée"))
    else:
        diagnostics.append(("good", "Processeur normal"))

    # Analyse de la RAM
    if ram >= 90:
        score -= 25
        diagnostics.append(("danger", "Mémoire vive presque saturée"))
    elif ram >= 75:
        score -= 10
        diagnostics.append(("warning", "Utilisation RAM élevée"))
    else:
        diagnostics.append(("good", "Mémoire vive normale"))

    # Analyse du stockage
    if disk >= 95:
        score -= 25
        diagnostics.append(("danger", "Disque presque plein"))
    elif disk >= 85:
        score -= 10
        diagnostics.append(("warning", "Espace disque faible"))
    else:
        diagnostics.append(("good", "Stockage suffisant"))

    # Le score reste toujours entre 0 et 100.
    score = max(0, min(100, score))

    if score >= 90:
        status = "EXCELLENT"
    elif score >= 75:
        status = "BON"
    elif score >= 50:
        status = "À SURVEILLER"
    else:
        status = "CRITIQUE"

    return {
        "score": score,
        "status": status,
        "diagnostics": diagnostics,
    }
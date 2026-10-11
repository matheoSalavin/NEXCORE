import sys
import psutil
import pyqtgraph as pg

from collections import deque
from PySide6.QtCore import Qt, QTimer
from services.process_manager import ProcessWorker, terminate_process
from services.system_monitor import get_system_metrics
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView, QLineEdit, QComboBox
)

# ============================================================
# FENÊTRE PRINCIPALE DE PC SENTINEL
# ============================================================

class PCSentinel(QMainWindow):
    """Contient les pages, les mesures et les interactions de l'application."""

    def __init__(self):
        super().__init__()

        # Configuration générale de la fenêtre.
        self.setWindowTitle("PC Sentinel")
        self.resize(1250, 780)
        self.setMinimumSize(1000, 650)

        # ----------------------------------------------------
        # Historique utilisé pour les graphiques
        # ----------------------------------------------------

        # Chaque graphique conserve les 60 dernières mesures.
        self.history_size = 60

        # deque conserve un nombre limité de valeurs.
        # Quand une nouvelle valeur arrive, la plus ancienne disparaît.
        self.cpu_history = deque(
            [0] * self.history_size,
            maxlen=self.history_size
        )
        self.ram_history = deque(
            [0] * self.history_size,
            maxlen=self.history_size
        )

        # Axe horizontal des graphiques : de -59 secondes à 0.
        self.seconds = deque(range(-59, 1), maxlen=self.history_size)

        # ----------------------------------------------------
        # Variables utilisées pour gérer les processus
        # ----------------------------------------------------

        self.process_worker = None

        # Indique si une nouvelle actualisation a été demandée
        # alors qu'une collecte était déjà en cours.
        self.process_request_pending = False

        # Permet de forcer la mise à jour de la liste des processus.
        self.force_process_refresh = False

        # Associe chaque PID aux informations de son processus.
        self.processes_by_pid = {}

        # Permet de distinguer le premier chargement des suivants.
        self.process_first_load = True

        # ----------------------------------------------------
        # Apparence générale de l'application
        # ----------------------------------------------------

        # Feuille de style inspirée des interfaces de monitoring.
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #080d18;
                color: #e6edf7;
                font-family: Segoe UI;
                font-size: 13px;
            }
            QFrame#sidebar {
                background-color: #0c1322;
                border-right: 1px solid #1d2b43;
            }
            QFrame#card, QFrame#panel {
                background-color: #101a2c;
                border: 1px solid #1d2e49;
                border-radius: 12px;
            }
            QLabel#muted { color: #8495b0; }
            QLabel#value {
                color: #55a6ff;
                font-size: 30px;
                font-weight: bold;
            }
            QLabel#heading {
                font-size: 23px;
                font-weight: bold;
            }
            QPushButton {
                background-color: transparent;
                color: #aab9d0;
                border: none;
                border-radius: 8px;
                padding: 12px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #162640;
                color: white;
            }
            QPushButton:checked {
                background-color: #17345b;
                color: #65b2ff;
                font-weight: bold;
            }
            QPushButton#danger {
                background-color: #8f2939;
                color: white;
                padding: 10px 16px;
            }
            QPushButton#danger:hover { background-color: #b83248; }
            QTableWidget {
                background-color: #0d1626;
                alternate-background-color: #101d30;
                border: 1px solid #1d2e49;
                border-radius: 8px;
                gridline-color: #1d2e49;
                selection-background-color: #173e6b;
                selection-color: white;
            }
            QHeaderView::section {
                background-color: #14233a;
                color: #9eb3d0;
                padding: 10px;
                border: none;
                border-bottom: 1px solid #263953;
            }
            QLineEdit, QComboBox {
                background-color: #0d1626;
                color: #e6edf7;
                border: 1px solid #263953;
                border-radius: 7px;
                padding: 9px;
            }
            QComboBox QAbstractItemView {
                background-color: #101a2c;
                color: #e6edf7;
                selection-background-color: #173e6b;
            }
        """)

        # ----------------------------------------------------
        # Création de la structure générale
        # ----------------------------------------------------

        central = QWidget()
        self.setCentralWidget(central)

        # L'interface est organisée horizontalement :
        # menu à gauche, contenu de la page à droite.
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ----------------------------------------------------
        # Menu latéral
        # ----------------------------------------------------

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 24, 16, 20)
        side.setSpacing(10)

        logo = QLabel("◈ PC SENTINEL")
        logo.setStyleSheet(
            "color: #55a6ff; font-size: 19px; font-weight: bold; padding: 8px;"
        )
        side.addWidget(logo)

        subtitle = QLabel("SURVEILLANCE SYSTÈME")
        subtitle.setObjectName("muted")
        subtitle.setStyleSheet("font-size: 10px; padding: 8px;")
        side.addWidget(subtitle)
        side.addSpacing(20)

        # Chaque bouton correspond à une page de l'application.
        self.nav_buttons = []
        nav_items = [
            ("⌂   Vue d'ensemble", 0),
            ("▥   Performances", 1),
            ("▤   Processus", 2),
        ]

        for label, index in nav_items:
            button = QPushButton(label)
            button.setCheckable(True)

            # La fonction appelée conserve l'index de la page
            # correspondant au bouton.
            button.clicked.connect(
                lambda checked=False, page=index: self.change_page(page)
            )

            side.addWidget(button)
            self.nav_buttons.append(button)

        # Place les informations de version en bas du menu.
        side.addStretch()

        version = QLabel("PC Sentinel 1.3\nMonitoring local")
        version.setObjectName("muted")
        version.setStyleSheet("padding: 8px;")
        side.addWidget(version)

        root.addWidget(sidebar)

        # ----------------------------------------------------
        # Pages principales
        # ----------------------------------------------------

        # QStackedWidget permet d'afficher une seule page à la fois.
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        # Création des trois pages.
        self.home_page = self.create_home_page()
        self.performance_page = self.create_performance_page()
        self.process_page = self.create_process_page()

        # Ajout des pages au conteneur.
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.performance_page)
        self.pages.addWidget(self.process_page)

        # Initialise le calcul du pourcentage CPU.
        # La première mesure sert notamment à préparer les suivantes.
        psutil.cpu_percent(interval=None)

        # ----------------------------------------------------
        # Actualisation automatique des données
        # ----------------------------------------------------

        # Les mesures générales sont mises à jour chaque seconde.
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_metrics)
        self.metrics_timer.start(1000)

        # La liste des processus est actualisée toutes les 5 secondes.
        self.process_timer = QTimer(self)
        self.process_timer.timeout.connect(self.request_process_update)
        self.process_timer.start(5000)

        # Effectue les premières mesures au démarrage.
        self.update_metrics()
        self.request_process_update()

        # Affiche la page d'accueil.
        self.change_page(0)

    # ========================================================
    # FONCTIONS DE CRÉATION DES ÉLÉMENTS GRAPHIQUES
    # ========================================================

    def create_card(self, title):
        """Crée une carte avec un titre, une valeur et un détail."""

        card = QFrame()
        card.setObjectName("card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        name = QLabel(title)
        name.setObjectName("muted")

        # Valeur principale, remplie lors de l'actualisation.
        value = QLabel("--")
        value.setObjectName("value")

        # Informations complémentaires sur la mesure.
        detail = QLabel("Chargement...")
        detail.setObjectName("muted")
        detail.setWordWrap(True)

        layout.addWidget(name)
        layout.addWidget(value)
        layout.addWidget(detail)
        layout.addStretch()

        # Retourne aussi les deux labels afin de pouvoir
        # modifier leurs textes depuis les autres fonctions.
        return card, value, detail

    def create_panel(self, title):
        """Crée un panneau contenant un titre et une mise en page verticale."""

        panel = QFrame()
        panel.setObjectName("panel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(heading)

        return panel, layout

    # ========================================================
    # PAGE 1 : VUE D'ENSEMBLE
    # ========================================================

    def create_home_page(self):
        """Construit la page qui résume l'état de l'ordinateur."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 20)
        layout.setSpacing(20)

        heading = QLabel("Vue d'ensemble")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        intro = QLabel("État de santé et activité de votre ordinateur")
        intro.setObjectName("muted")
        layout.addWidget(intro)

        # Trois cartes : processeur, mémoire vive et stockage.
        cards = QHBoxLayout()
        cards.setSpacing(16)

        cpu_card, self.cpu_value, self.cpu_detail = self.create_card(
            "PROCESSEUR"
        )
        ram_card, self.ram_value, self.ram_detail = self.create_card(
            "MÉMOIRE VIVE"
        )
        disk_card, self.disk_value, self.disk_detail = self.create_card(
            "STOCKAGE"
        )

        cards.addWidget(cpu_card)
        cards.addWidget(ram_card)
        cards.addWidget(disk_card)
        layout.addLayout(cards)

        # Panneau consacré aux informations générales du PC.
        panel, panel_layout = self.create_panel("Informations système")

        self.system_info = QLabel("Collecte des informations...")
        self.system_info.setObjectName("muted")

        # Autorise la sélection du texte pour pouvoir le copier.
        self.system_info.setTextInteractionFlags(Qt.TextSelectableByMouse)

        panel_layout.addWidget(self.system_info)
        layout.addWidget(panel)
        layout.addStretch()

        # Message indiquant l'état de la collecte.
        self.home_status = QLabel("Initialisation des mesures...")
        self.home_status.setObjectName("muted")
        layout.addWidget(self.home_status)

        return page

    # ========================================================
    # PAGE 2 : PERFORMANCES
    # ========================================================

    def style_graph(self, graph, color):
        """Applique le style commun aux graphiques de performances."""

        graph.setBackground("#101a2c")
        graph.showGrid(x=True, y=True, alpha=0.2)

        # Les valeurs affichées sur l'axe vertical vont de 0 à 100 %.
        graph.setYRange(0, 100)

        # L'axe horizontal représente les 60 dernières secondes.
        graph.setXRange(-59, 0)

        graph.setLabel("left", "Utilisation", units="%")
        graph.setLabel("bottom", "Temps", units="s")

        # Couleur des axes et de leurs graduations.
        graph.getAxis("left").setTextPen("#8495b0")
        graph.getAxis("bottom").setTextPen("#8495b0")
        graph.getAxis("left").setPen("#34435a")
        graph.getAxis("bottom").setPen("#34435a")
        graph.getViewBox().setBorder("#263953")

        # Trace une courbe initiale à zéro.
        graph.plot(
            list(self.seconds),
            [0] * self.history_size,
            pen=pg.mkPen(color=color, width=2.5)
        )

    def create_performance_page(self):
        """Construit la page affichant l'évolution du CPU et de la RAM."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 20)
        layout.setSpacing(16)

        heading = QLabel("Performances en temps réel")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        intro = QLabel("Historique glissant des 60 dernières secondes")
        intro.setObjectName("muted")
        layout.addWidget(intro)

        # Graphique du processeur.
        cpu_panel, cpu_layout = self.create_panel(
            "Processeur — utilisation"
        )

        self.cpu_graph = pg.PlotWidget()
        self.cpu_graph.setMinimumHeight(170)
        self.style_graph(self.cpu_graph, "#55a6ff")
        cpu_layout.addWidget(self.cpu_graph)

        self.cpu_current = QLabel("Utilisation actuelle : --%")
        self.cpu_current.setObjectName("muted")
        cpu_layout.addWidget(self.cpu_current)
        layout.addWidget(cpu_panel, 1)

        # Graphique de la mémoire vive.
        ram_panel, ram_layout = self.create_panel(
            "Mémoire vive — utilisation"
        )

        self.ram_graph = pg.PlotWidget()
        self.ram_graph.setMinimumHeight(170)
        self.style_graph(self.ram_graph, "#a78bfa")
        ram_layout.addWidget(self.ram_graph)

        self.ram_current = QLabel("Utilisation actuelle : --%")
        self.ram_current.setObjectName("muted")
        ram_layout.addWidget(self.ram_current)
        layout.addWidget(ram_panel, 1)

        # Ces objets représentent les courbes qui seront actualisées
        # à chaque nouvelle mesure.
        self.cpu_line = self.cpu_graph.plot(
            list(self.seconds),
            list(self.cpu_history),
            pen=pg.mkPen("#55a6ff", width=2.5)
        )

        self.ram_line = self.ram_graph.plot(
            list(self.seconds),
            list(self.ram_history),
            pen=pg.mkPen("#a78bfa", width=2.5)
        )

        return page

    # ========================================================
    # PAGE 3 : GESTION DES PROCESSUS
    # ========================================================

    def create_process_page(self):
        """Construit la liste des processus et ses commandes."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 20)
        layout.setSpacing(14)

        heading = QLabel("Processus en cours")
        heading.setObjectName("heading")
        layout.addWidget(heading)

        intro = QLabel(
            "Programmes actifs et consommation des ressources. "
            "Collecte en arrière-plan toutes les 5 secondes."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.process_summary = QLabel("Recherche des processus...")
        self.process_summary.setObjectName("muted")
        layout.addWidget(self.process_summary)

        # ----------------------------------------------------
        # Barre de recherche et filtres
        # ----------------------------------------------------

        filters = QHBoxLayout()

        self.process_search = QLineEdit()
        self.process_search.setPlaceholderText(
            "Rechercher un processus..."
        )
        self.process_search.setClearButtonEnabled(True)

        # Chaque changement du texte applique immédiatement le filtre.
        self.process_search.textChanged.connect(self.filter_processes)
        filters.addWidget(self.process_search, 1)

        self.process_filter = QComboBox()
        self.process_filter.addItems([
            "Tous les processus",
            "CPU supérieur à 5 %",
            "RAM supérieure à 500 Mo"
        ])

        self.process_filter.currentIndexChanged.connect(
            self.filter_processes
        )
        filters.addWidget(self.process_filter)
        layout.addLayout(filters)

        # ----------------------------------------------------
        # Tableau des processus
        # ----------------------------------------------------

        self.process_table = QTableWidget(0, 4)
        self.process_table.setHorizontalHeaderLabels(
            ["Nom du processus", "PID", "CPU (%)", "RAM (Mo)"]
        )
        self.process_table.setAlternatingRowColors(True)

        # La sélection porte sur une ligne entière.
        self.process_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.process_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        # Empêche la modification manuelle des valeurs du tableau.
        self.process_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.process_table.setSortingEnabled(False)
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setWordWrap(False)

        # Ajuste la largeur des colonnes au contenu.
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

        for column in (1, 2, 3):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

        layout.addWidget(self.process_table, 1)

        # ----------------------------------------------------
        # Boutons d'action
        # ----------------------------------------------------

        actions = QHBoxLayout()

        self.process_status = QLabel(
            "Sélectionne un processus pour agir."
        )
        self.process_status.setObjectName("muted")

        self.refresh_button = QPushButton("Actualiser")
        self.refresh_button.clicked.connect(
            self.refresh_processes_manually
        )

        self.stop_button = QPushButton(
            "Terminer le processus sélectionné"
        )
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self.stop_selected_process)

        actions.addWidget(self.process_status, 1)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.stop_button)
        layout.addLayout(actions)

        return page

    # ========================================================
    # NAVIGATION ENTRE LES PAGES
    # ========================================================

    def change_page(self, index):
        """Affiche la page demandée et met à jour le menu latéral."""

        self.pages.setCurrentIndex(index)

        # Le bouton de la page affichée est marqué comme sélectionné.
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

        # Actualise les processus lorsque l'utilisateur ouvre cette page.
        if index == 2:
            self.request_process_update()

    # ========================================================
    # ACTUALISATION DES MESURES DU PC
    # ========================================================

    def update_metrics(self):
        """Récupère les mesures système et actualise les affichages."""

        try:
            # Utilisation actuelle du processeur en pourcentage.
            metrics = get_system_metrics()
            cpu = metrics["cpu"]

            # Informations sur la mémoire vive.
            memory = type("Memory", (), {
                "percent": metrics["ram_percent"],
                "used": metrics["ram_used"],
                "total": metrics["ram_total"]
            })()

            # Informations sur le disque C:.
            disk = type("Disk", (), {
                "percent": metrics["disk_percent"],
                "free": metrics["disk_free"],
                "total": metrics["disk_total"]
            })()

            # Mise à jour de la carte processeur.
            self.cpu_value.setText(f"{cpu:.0f}%")
            self.cpu_detail.setText(
                f"{psutil.cpu_count(logical=True)} processeurs logiques"
            )

            # Mise à jour de la carte mémoire vive.
            self.ram_value.setText(f"{memory.percent:.0f}%")
            self.ram_detail.setText(
                f"{memory.used / (1024 ** 3):.1f} Go utilisés sur "
                f"{memory.total / (1024 ** 3):.1f} Go"
            )

            # Mise à jour de la carte stockage.
            self.disk_value.setText(f"{disk.percent:.0f}%")
            self.disk_detail.setText(
                f"{disk.free / (1024 ** 3):.1f} Go libres sur "
                f"{disk.total / (1024 ** 3):.1f} Go"
            )

            # Fréquence actuelle du processeur, si elle est disponible.
            frequency = psutil.cpu_freq()

            frequency_text = (
                f"{frequency.current:.0f} MHz"
                if frequency else "Indisponible"
            )

            # Informations générales présentées sur la page d'accueil.
            self.system_info.setText(
                f"Système : Windows\n"
                f"Processeurs logiques : {psutil.cpu_count(logical=True)}\n"
                f"Fréquence CPU : {frequency_text}\n"
                f"Mémoire totale : {memory.total / (1024 ** 3):.1f} Go"
            )

            # Ajoute les nouvelles valeurs à l'historique.
            # Les plus anciennes sont supprimées automatiquement
            # lorsque la limite de 60 mesures est atteinte.
            self.cpu_history.append(cpu)
            self.ram_history.append(memory.percent)
            self.seconds.append(self.seconds[-1] + 1)

            # Redessine les deux courbes avec les dernières données.
            self.cpu_line.setData(
                list(self.seconds), list(self.cpu_history)
            )
            self.ram_line.setData(
                list(self.seconds), list(self.ram_history)
            )

            # Affiche les valeurs actuelles sous les graphiques.
            self.cpu_current.setText(
                f"Utilisation actuelle : {cpu:.1f}%"
            )
            self.ram_current.setText(
                f"Utilisation actuelle : {memory.percent:.1f}% "
                f"({memory.used / (1024 ** 3):.1f} Go utilisés)"
            )

            self.home_status.setText(
                "● Système opérationnel — mesures actualisées chaque seconde"
            )

        except Exception as error:
            # Affiche l'erreur plutôt que de faire planter l'application.
            self.home_status.setText(f"Erreur de mesure : {error}")

    # ========================================================
    # ACTUALISATION DE LA LISTE DES PROCESSUS
    # ========================================================

    def refresh_processes_manually(self):
        """Force une actualisation demandée par l'utilisateur."""

        self.force_process_refresh = True
        self.request_process_update()

    def request_process_update(self):
        """Lance la collecte si aucun autre thread ne travaille déjà."""

        # Évite de lancer plusieurs collectes simultanément.
        if (
            self.process_worker is not None
            and self.process_worker.isRunning()
        ):
            self.process_request_pending = True
            return

        self.process_request_pending = False
        self.refresh_button.setEnabled(False)

        # Le worker effectue la collecte sans bloquer l'interface.
        self.process_worker = ProcessWorker(self)

        # Connexion des signaux du worker aux fonctions de l'interface.
        self.process_worker.results_ready.connect(self.receive_processes)
        self.process_worker.error_occurred.connect(self.process_error)
        self.process_worker.finished.connect(
            self.process_worker_finished
        )

        self.process_worker.start()

    def process_worker_finished(self):
        """Réactive le bouton et traite une éventuelle demande en attente."""

        self.refresh_button.setEnabled(True)

        # Si une actualisation a été demandée pendant la collecte,
        # en lance une nouvelle après un court délai.
        if self.process_request_pending:
            self.process_request_pending = False
            QTimer.singleShot(100, self.request_process_update)

    def process_error(self, message):
        """Affiche une erreur si la lecture des processus échoue."""

        self.process_summary.setText(f"Erreur de lecture : {message}")

    def receive_processes(self, processes):
        """Reçoit les résultats et met à jour le tableau."""

        table = self.process_table

        # Mémorise le PID sélectionné pour tenter de conserver
        # la sélection après l'actualisation du tableau.
        selected_pid = None
        current_row = table.currentRow()

        if current_row >= 0:
            pid_item = table.item(current_row, 1)

            if pid_item:
                selected_pid = pid_item.data(Qt.ItemDataRole.UserRole)

        # Si un processus est sélectionné, on évite de reconstruire
        # le tableau automatiquement pour ne pas déplacer la sélection.
        # Les données reçues sont néanmoins conservées en mémoire.
        if (
            selected_pid is not None
            and not self.process_first_load
            and not self.force_process_refresh
        ):
            self.processes_by_pid = {
                pid: (name, cpu, ram_mb)
                for name, pid, cpu, ram_mb in processes
            }

            self.process_summary.setText(
                f"{len(processes)} processus détectés — sélection verrouillée "
                "(clique sur Actualiser après avoir désélectionné)"
            )
            return

        # Conserve les informations dans un dictionnaire indexé par PID.
        self.processes_by_pid = {
            pid: (name, cpu, ram_mb)
            for name, pid, cpu, ram_mb in processes
        }

        # Désactive temporairement le rafraîchissement visuel
        # pour éviter des mises à jour inutiles pendant le remplissage.
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        table.clearContents()
        table.setRowCount(len(processes))

        selected_row = -1

        # Remplit le tableau avec les nouveaux résultats.
        for row, (name, pid, cpu, ram_mb) in enumerate(processes):
            values = [name, str(pid), f"{cpu:.1f}", f"{ram_mb:.1f}"]

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)

                # Aligne les données numériques à droite.
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )

                # Enregistre le PID réel dans la cellule.
                # Il reste ainsi accessible même si le texte est modifié.
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, pid)

                table.setItem(row, column, item)

            # Repère la ligne correspondant à l'ancien processus sélectionné.
            if pid == selected_pid:
                selected_row = row

        table.setUpdatesEnabled(True)

        # Restaure la sélection si le processus existe toujours.
        if selected_row >= 0:
            table.selectRow(selected_row)

        self.process_first_load = False
        self.force_process_refresh = False

        # Réapplique les filtres après le remplacement des lignes.
        self.filter_processes()

        self.process_summary.setText(
            f"{len(processes)} processus détectés — tri par consommation RAM"
        )

    # ========================================================
    # RECHERCHE ET FILTRAGE DES PROCESSUS
    # ========================================================

    def filter_processes(self, *args):
        """Masque les lignes qui ne correspondent pas aux critères."""

        # Vérifie que le tableau existe avant de le parcourir.
        if not hasattr(self, "process_table"):
            return

        # Récupère les critères saisis par l'utilisateur.
        search = self.process_search.text().strip().lower()
        filter_index = self.process_filter.currentIndex()

        for row in range(self.process_table.rowCount()):
            name_item = self.process_table.item(row, 0)
            cpu_item = self.process_table.item(row, 2)
            ram_item = self.process_table.item(row, 3)

            # Ignore une ligne si ses informations ne sont pas disponibles.
            if not name_item or not cpu_item or not ram_item:
                continue

            name = name_item.text().lower()
            cpu = float(cpu_item.text())
            ram = float(ram_item.text())

            # Le nom doit correspondre à la recherche.
            visible = search in name

            # Applique éventuellement un filtre supplémentaire.
            if filter_index == 1:
                visible = visible and cpu > 5
            elif filter_index == 2:
                visible = visible and ram > 500

            # Masque la ligne si elle ne correspond pas aux critères.
            self.process_table.setRowHidden(row, not visible)

    # ========================================================
    # ARRÊT D'UN PROCESSUS
    # ========================================================

    def stop_selected_process(self):
        """Demande confirmation puis tente d'arrêter le processus choisi."""

        row = self.process_table.currentRow()

        # Vérifie qu'une ligne est sélectionnée.
        if row < 0:
            QMessageBox.information(
                self,
                "Aucun processus sélectionné",
                "Sélectionne d'abord un processus dans la liste."
            )
            return

        pid_item = self.process_table.item(row, 1)
        name_item = self.process_table.item(row, 0)

        if pid_item is None or name_item is None:
            return

        # Récupère le PID et le nom du processus choisi.
        pid = pid_item.data(Qt.ItemDataRole.UserRole)
        name = name_item.text()

        # Empêche l'application de tenter de s'arrêter elle-même.
        if pid == psutil.Process().pid:
            QMessageBox.warning(
                self,
                "Action impossible",
                "PC Sentinel ne peut pas terminer son propre processus."
            )
            return

        # Demande une confirmation avant toute action.
        # Cela évite un arrêt accidentel et une éventuelle perte de données.
        answer = QMessageBox.question(
            self,
            "Confirmer l'arrêt",
            f"Veux-tu vraiment terminer « {name} » (PID {pid}) ?\n\n"
            "Cela peut entraîner la perte de données non enregistrées "
            "dans le programme concerné.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            # Récupère le processus à partir de son PID.
            process = psutil.Process(pid)

            # Vérifie que le PID correspond toujours au même nom.
            # Un PID peut être réutilisé après la fermeture d'un processus.
            if process.name() != name:
                QMessageBox.warning(
                    self,
                    "Processus modifié",
                    "Ce PID correspond maintenant à un autre processus. "
                    "Actualise la liste et réessaie."
                )
                return

            # Demande à Windows de terminer le processus.
            process.terminate()

            try:
                # Attend jusqu'à 3 secondes pour vérifier son arrêt.
                process.wait(timeout=3)

            except psutil.TimeoutExpired:
                # Aucun arrêt forcé n'est effectué automatiquement.
                QMessageBox.warning(
                    self,
                    "Arrêt en attente",
                    "Le processus ne s'est pas arrêté dans les 3 secondes. "
                    "Aucun arrêt forcé n'a été tenté."
                )
                return

            # Informe l'utilisateur et actualise la liste.
            self.process_status.setText(
                f"Processus « {name} » terminé."
            )
            self.process_table.clearSelection()
            self.process_table.setCurrentCell(-1, -1)
            self.request_process_update()

        except psutil.NoSuchProcess:
            # Le processus a pu se fermer entre-temps.
            self.process_status.setText("Ce processus est déjà arrêté.")
            self.process_table.clearSelection()
            self.process_table.setCurrentCell(-1, -1)
            self.request_process_update()

        except psutil.AccessDenied:
            # Windows peut interdire l'arrêt de certains processus.
            QMessageBox.warning(
                self,
                "Accès refusé",
                "Windows refuse l'arrêt de ce processus. "
                "Certains processus nécessitent des droits administrateur."
            )

        except Exception as error:
            # Affiche les autres erreurs rencontrées.
            QMessageBox.warning(
                self,
                "Erreur",
                f"Impossible d'arrêter ce processus : {error}"
            )


# ============================================================
# POINT D'ENTRÉE DU PROGRAMME
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PCSentinel()
    window.show()
    sys.exit(app.exec())
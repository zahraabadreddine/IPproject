#!/usr/bin/env python3
"""
Calculateur de Sous-Réseaux IP (IPv4 & IPv6) — Interface graphique
====================================================================

Interface graphique Tkinter (inclus nativement dans Python, aucune
dépendance supplémentaire) pour le même moteur de calcul que la version
CLI (subnet_calculator.py). Elle réutilise directement les fonctions de
calcul de ce module pour garantir des résultats identiques.

Auteur : Zahraa Badreddine
Licence : MIT
"""

import ipaddress
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from subnet_calculator import mask_to_binary, get_address_type, get_usable_hosts

# Libellés affichés dans le tableau de résultats, dans l'ordre voulu.
FIELD_ORDER_IPV4 = [
    "Adresse saisie", "Version", "Adresse réseau", "Préfixe CIDR",
    "Masque (décimal)", "Masque (binaire)", "Adresse de broadcast",
    "Première IP utilisable", "Dernière IP utilisable",
    "Nombre total d'hôtes", "Type de l'adresse saisie",
]
FIELD_ORDER_IPV6 = [
    "Adresse saisie", "Version", "Adresse réseau", "Préfixe CIDR",
    "Masque (binaire)",
    "Première IP utilisable", "Dernière IP utilisable",
    "Nombre total d'hôtes", "Type de l'adresse saisie",
]


class SubnetCalculatorApp(tk.Tk):
    """Fenêtre principale de l'application."""

    def __init__(self):
        super().__init__()

        self.title("Calculateur de Sous-Réseaux IP (IPv4 & IPv6)")
        self.geometry("640x480")
        self.minsize(560, 420)
        self.configure(bg="#1e1e2e")

        self._build_style()
        self._build_widgets()

    # ------------------------------------------------------------------ #
    # Construction de l'interface
    # ------------------------------------------------------------------ #

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        bg = "#1e1e2e"
        panel = "#282838"
        accent = "#7aa2f7"
        text = "#e6e6f0"

        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=bg, foreground=accent, font=("Segoe UI", 15, "bold"))
        style.configure("Subtitle.TLabel", background=bg, foreground="#9a9ab0", font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground=panel, foreground=text)
        style.configure(
            "TButton", background=accent, foreground="#101018",
            font=("Segoe UI", 10, "bold"), padding=6, borderwidth=0,
        )
        style.map("TButton", background=[("active", "#5f85e0")])
        style.configure(
            "Treeview", background=panel, fieldbackground=panel, foreground=text,
            rowheight=26, font=("Consolas", 10), borderwidth=0,
        )
        style.configure(
            "Treeview.Heading", background="#33334a", foreground=accent,
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", "#3d3d5c")])

    def _build_widgets(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Calculateur de Sous-Réseaux IP", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Compatible IPv4 & IPv6 — propulsé par le module Python `ipaddress`",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 14))

        # Zone de saisie
        input_frame = ttk.Frame(container)
        input_frame.pack(fill="x", pady=(0, 10))

        self.entry = ttk.Entry(input_frame, font=("Consolas", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.insert(0, "192.168.1.45/24")
        self.entry.bind("<Return>", lambda _event: self.on_calculate())
        self.entry.focus()

        calc_btn = ttk.Button(input_frame, text="Calculer", command=self.on_calculate)
        calc_btn.pack(side="left", padx=(8, 0))

        # Tableau de résultats
        self.tree = ttk.Treeview(container, columns=("valeur",), show="tree headings")
        self.tree.heading("#0", text="Propriété")
        self.tree.heading("valeur", text="Valeur")
        self.tree.column("#0", width=200, anchor="w")
        self.tree.column("valeur", width=320, anchor="w")
        self.tree.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Astuce : appuyez sur Entrée pour calculer.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ #
    # Logique
    # ------------------------------------------------------------------ #

    def on_calculate(self) -> None:
        ip_input = self.entry.get().strip()
        self.tree.delete(*self.tree.get_children())

        if not ip_input:
            return

        try:
            interface = ipaddress.ip_interface(ip_input)
            network = interface.network
        except ValueError:
            messagebox.showerror(
                "Entrée invalide",
                "Le format saisi n'est pas une adresse IP/CIDR valide.\n"
                "Exemples attendus : 192.168.1.45/24  ou  2001:db8::/32",
            )
            return

        version_label = "IPv4" if network.version == 4 else "IPv6"
        host_ip = interface.ip
        first_usable, last_usable, total_hosts = get_usable_hosts(network)

        values = {
            "Adresse saisie": ip_input,
            "Version": version_label,
            "Adresse réseau": str(network.network_address),
            "Préfixe CIDR": f"/{network.prefixlen}",
            "Première IP utilisable": str(first_usable),
            "Dernière IP utilisable": str(last_usable),
            "Nombre total d'hôtes": f"{total_hosts:,}".replace(",", " "),
            "Type de l'adresse saisie": get_address_type(host_ip),
        }

        if network.version == 4:
            values["Masque (décimal)"] = str(network.netmask)
            values["Masque (binaire)"] = mask_to_binary(network)
            values["Adresse de broadcast"] = str(network.broadcast_address)
            field_order = FIELD_ORDER_IPV4
        else:
            values["Masque (binaire)"] = mask_to_binary(network)
            field_order = FIELD_ORDER_IPV6

        for field in field_order:
            self.tree.insert("", "end", text=field, values=(values[field],))


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    app = SubnetCalculatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()

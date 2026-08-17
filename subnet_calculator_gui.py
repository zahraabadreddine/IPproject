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
from tkinter import filedialog, messagebox, ttk

from subnet_calculator import (
    build_result_dict,
    export_results_csv,
    export_results_json,
    split_network,
)

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

        # Zone de découpage en sous-réseaux
        split_frame = ttk.Frame(container)
        split_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(split_frame, text="Diviser en :").pack(side="left")
        self.split_entry = ttk.Entry(split_frame, font=("Consolas", 11), width=6)
        self.split_entry.pack(side="left", padx=(6, 0), ipady=4)
        ttk.Label(split_frame, text="sous-réseaux").pack(side="left", padx=(6, 0))

        split_btn = ttk.Button(split_frame, text="Diviser", command=self.on_split)
        split_btn.pack(side="left", padx=(8, 0))

        export_csv_btn = ttk.Button(split_frame, text="Exporter CSV", command=self.on_export_csv)
        export_csv_btn.pack(side="right")
        export_json_btn = ttk.Button(split_frame, text="Exporter JSON", command=self.on_export_json)
        export_json_btn.pack(side="right", padx=(0, 8))

        # Tableau de résultats
        self.tree = ttk.Treeview(container, columns=("valeur",), show="tree headings")
        self.tree.heading("#0", text="Propriété")
        self.tree.heading("valeur", text="Valeur")
        self.tree.column("#0", width=200, anchor="w")
        self.tree.column("valeur", width=320, anchor="w")
        self.tree.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Astuce : appuyez sur Entrée pour calculer. Le découpage et l'export "
                 "s'appliquent au dernier résultat calculé.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        self.last_rows: list = []

    # ------------------------------------------------------------------ #
    # Logique
    # ------------------------------------------------------------------ #

    def _parse_network(self, ip_input: str):
        interface = ipaddress.ip_interface(ip_input)
        return interface.network

    def _configure_tree_single(self) -> None:
        self.tree["columns"] = ("valeur",)
        self.tree["show"] = "tree headings"
        self.tree.heading("#0", text="Propriété")
        self.tree.heading("valeur", text="Valeur")
        self.tree.column("#0", width=200, anchor="w")
        self.tree.column("valeur", width=320, anchor="w")

    def _configure_tree_split(self) -> None:
        columns = ("reseau", "prefixe", "premiere", "derniere", "hotes")
        self.tree["columns"] = columns
        self.tree["show"] = "headings"
        headings = {
            "reseau": "Adresse réseau",
            "prefixe": "Préfixe",
            "premiere": "Première IP",
            "derniere": "Dernière IP",
            "hotes": "Hôtes",
        }
        widths = {"reseau": 160, "prefixe": 70, "premiere": 140, "derniere": 140, "hotes": 90}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")

    def on_calculate(self) -> None:
        ip_input = self.entry.get().strip()
        self.tree.delete(*self.tree.get_children())
        self._configure_tree_single()

        if not ip_input:
            return

        try:
            network = self._parse_network(ip_input)
        except ValueError:
            messagebox.showerror(
                "Entrée invalide",
                "Le format saisi n'est pas une adresse IP/CIDR valide.\n"
                "Exemples attendus : 192.168.1.45/24  ou  2001:db8::/32",
            )
            return

        values = build_result_dict(network, ip_input)
        field_order = FIELD_ORDER_IPV4 if network.version == 4 else FIELD_ORDER_IPV6

        for field in field_order:
            self.tree.insert("", "end", text=field, values=(values[field],))

        self.last_rows = [values]

    def on_split(self) -> None:
        ip_input = self.entry.get().strip()
        n_text = self.split_entry.get().strip()

        if not ip_input or not n_text:
            messagebox.showerror(
                "Entrée manquante",
                "Saisissez une adresse IP/CIDR et un nombre de sous-réseaux.",
            )
            return

        try:
            network = self._parse_network(ip_input)
        except ValueError:
            messagebox.showerror(
                "Entrée invalide",
                "Le format saisi n'est pas une adresse IP/CIDR valide.",
            )
            return

        try:
            num_subnets = int(n_text)
            subnets = split_network(network, num_subnets=num_subnets)
        except ValueError as error:
            messagebox.showerror("Découpage impossible", str(error))
            return

        self.tree.delete(*self.tree.get_children())
        self._configure_tree_split()

        self.last_rows = []
        for subnet in subnets:
            row = build_result_dict(subnet, str(subnet))
            self.last_rows.append(row)
            self.tree.insert(
                "", "end",
                values=(
                    row["Adresse réseau"],
                    row["Préfixe CIDR"],
                    row["Première IP utilisable"],
                    row["Dernière IP utilisable"],
                    row["Nombre total d'hôtes"],
                ),
            )

    def on_export_csv(self) -> None:
        if not self.last_rows:
            messagebox.showerror("Rien à exporter", "Calculez d'abord un résultat.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Fichier CSV", "*.csv")],
        )
        if not path:
            return
        export_results_csv(self.last_rows, path)
        messagebox.showinfo("Export réussi", f"Résultats exportés vers :\n{path}")

    def on_export_json(self) -> None:
        if not self.last_rows:
            messagebox.showerror("Rien à exporter", "Calculez d'abord un résultat.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Fichier JSON", "*.json")],
        )
        if not path:
            return
        export_results_json(self.last_rows, path)
        messagebox.showinfo("Export réussi", f"Résultats exportés vers :\n{path}")


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

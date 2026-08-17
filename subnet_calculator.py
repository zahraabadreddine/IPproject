#!/usr/bin/env python3
"""
Calculateur de Sous-Réseaux IP (IPv4 & IPv6)
=============================================

Outil en ligne de commande qui calcule et affiche les informations
essentielles d'un réseau à partir d'une adresse IP saisie au format CIDR
(ex: 192.168.1.45/24 ou 2001:db8::/32).

Auteur : Zahraa Badreddine
Licence : MIT
"""

import argparse
import csv
import ipaddress
import json
import math
import sys
from pathlib import Path

# Sur Windows, la console utilise par défaut un encodage (cp1252) qui ne
# gère pas bien les caractères accentués. On force l'UTF-8 pour un affichage
# correct des textes en français.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


# --------------------------------------------------------------------------- #
# Fonctions de calcul réseau
# --------------------------------------------------------------------------- #

def mask_to_binary(network: ipaddress.IPv4Network | ipaddress.IPv6Network) -> str:
    """
    Convertit le masque de sous-réseau en une représentation binaire lisible.

    Pour IPv4, le résultat est découpé en 4 groupes de 8 bits (ex: 11111111.11111111.11111111.00000000).
    Pour IPv6, le résultat est découpé en groupes de 16 bits pour rester lisible.
    """
    netmask_int = int(network.netmask)

    if network.version == 4:
        bits = format(netmask_int, "032b")
        return ".".join(bits[i:i + 8] for i in range(0, 32, 8))
    else:
        bits = format(netmask_int, "0128b")
        return ":".join(bits[i:i + 16] for i in range(0, 128, 16))


def get_address_type(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """
    Détermine le type de l'adresse IP : Loopback, Privée ou Publique.

    On teste d'abord les cas particuliers (loopback, lien-local, multicast, etc.)
    car ils sont "is_private" == True mais méritent un libellé plus précis.
    """
    if ip.is_loopback:
        return "Loopback"
    if ip.is_link_local:
        return "Lien-local (APIPA / IPv6 link-local)"
    if ip.is_multicast:
        return "Multicast"
    if ip.is_reserved:
        return "Réservée"
    if ip.is_unspecified:
        return "Non spécifiée"
    if ip.is_private:
        return "Privée"
    return "Publique"


def get_usable_hosts(network: ipaddress.IPv4Network | ipaddress.IPv6Network):
    """
    Calcule la première et la dernière adresse IP attribuable (utilisable) du réseau,
    ainsi que le nombre total d'hôtes disponibles.

    Règles IPv4 :
      - Un réseau /31 ou /32 n'a pas d'adresse réseau/broadcast "classique"
        (RFC 3021 pour les liaisons point-à-point). On gère ce cas séparément.
      - Sinon, la plage utilisable exclut l'adresse réseau et l'adresse de broadcast.

    Règles IPv6 :
      - Il n'y a pas de notion de broadcast en IPv6. Toutes les adresses de la
        plage sont potentiellement utilisables, hormis l'adresse réseau elle-même
        (adresse "tous zéros"), par convention.
    """
    if network.version == 4:
        if network.prefixlen >= 31:
            # /31 (2 adresses, point-à-point) ou /32 (hôte unique)
            hosts = list(network.hosts())
            if not hosts:
                # /32 : une seule adresse, elle est à la fois réseau et hôte
                first_usable = last_usable = network.network_address
                total_hosts = 1
            else:
                first_usable, last_usable = hosts[0], hosts[-1]
                total_hosts = len(hosts)
        else:
            first_usable = network.network_address + 1
            last_usable = network.broadcast_address - 1
            total_hosts = network.num_addresses - 2
    else:
        # IPv6 : pas de broadcast, on exclut uniquement l'adresse réseau
        total_hosts = network.num_addresses - 1
        first_usable = network.network_address + 1 if network.num_addresses > 1 else network.network_address
        last_usable = network[-1]

    return first_usable, last_usable, total_hosts


def build_result_dict(network: ipaddress.IPv4Network | ipaddress.IPv6Network, ip_input: str) -> dict:
    """
    Construit un dictionnaire plat regroupant toutes les informations calculées
    pour un réseau. Utilisé comme source commune pour l'export CSV/JSON et le
    mode batch, en plus de l'affichage.
    """
    version_label = "IPv4" if network.version == 4 else "IPv6"
    host_ip = ipaddress.ip_interface(ip_input).ip
    first_usable, last_usable, total_hosts = get_usable_hosts(network)

    return {
        "Adresse saisie": ip_input,
        "Version": version_label,
        "Adresse réseau": str(network.network_address),
        "Préfixe CIDR": f"/{network.prefixlen}",
        "Masque (décimal)": str(network.netmask) if network.version == 4 else "-",
        "Masque (binaire)": mask_to_binary(network),
        "Adresse de broadcast": str(network.broadcast_address) if network.version == 4 else "-",
        "Première IP utilisable": str(first_usable),
        "Dernière IP utilisable": str(last_usable),
        "Nombre total d'hôtes": total_hosts,
        "Type de l'adresse saisie": get_address_type(host_ip),
    }


# --------------------------------------------------------------------------- #
# Découpage (subnetting) et agrégation (supernetting)
# --------------------------------------------------------------------------- #

def split_network(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    num_subnets: int | None = None,
    new_prefix: int | None = None,
) -> list:
    """
    Découpe un réseau en sous-réseaux plus petits, soit :
      - en précisant `num_subnets` : le nombre de sous-réseaux égaux souhaités
        (le préfixe est agrandi du nombre de bits nécessaire, arrondi à la
        puissance de 2 supérieure) ;
      - en précisant `new_prefix` directement : la longueur de préfixe cible.

    Un seul des deux paramètres doit être fourni.
    """
    if (num_subnets is None) == (new_prefix is None):
        raise ValueError("Précisez soit un nombre de sous-réseaux, soit un nouveau préfixe (un seul des deux).")

    max_prefix = 32 if network.version == 4 else 128

    if num_subnets is not None:
        if num_subnets < 1:
            raise ValueError("Le nombre de sous-réseaux doit être supérieur ou égal à 1.")
        extra_bits = math.ceil(math.log2(num_subnets)) if num_subnets > 1 else 0
        new_prefix = network.prefixlen + extra_bits

    if new_prefix <= network.prefixlen:
        raise ValueError(
            f"Le nouveau préfixe (/{new_prefix}) doit être strictement plus grand "
            f"que le préfixe d'origine (/{network.prefixlen})."
        )
    if new_prefix > max_prefix:
        raise ValueError(f"Le nouveau préfixe (/{new_prefix}) dépasse la taille maximale (/{max_prefix}).")

    return list(network.subnets(new_prefix=new_prefix))


def supernet_networks(cidrs: list) -> list:
    """
    Agrège (supernet) une liste d'adresses réseau/CIDR en le plus petit
    ensemble de blocs contigus les recouvrant, via ipaddress.collapse_addresses.
    """
    networks = [ipaddress.ip_network(cidr, strict=False) for cidr in cidrs]
    return list(ipaddress.collapse_addresses(networks))


# --------------------------------------------------------------------------- #
# Export (CSV / JSON)
# --------------------------------------------------------------------------- #

def export_results_csv(rows: list, path) -> None:
    """Exporte une liste de dictionnaires de résultats vers un fichier CSV."""
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_results_json(rows: list, path) -> None:
    """Exporte une liste de dictionnaires de résultats vers un fichier JSON."""
    with open(path, "w", encoding="utf-8") as json_file:
        json.dump(rows, json_file, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Affichage (rich)
# --------------------------------------------------------------------------- #

def display_results(network: ipaddress.IPv4Network | ipaddress.IPv6Network, ip_input: str) -> None:
    """Construit et affiche un tableau récapitulatif des informations du réseau."""

    version_label = "IPv4" if network.version == 4 else "IPv6"
    host_ip = ipaddress.ip_interface(ip_input).ip

    first_usable, last_usable, total_hosts = get_usable_hosts(network)

    table = Table(
        title=f"Résultats du calcul — {version_label}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("Propriété", style="bold white", no_wrap=True)
    table.add_column("Valeur", style="green")

    table.add_row("Adresse saisie", ip_input)
    table.add_row("Version", version_label)
    table.add_row("Adresse réseau", str(network.network_address))
    table.add_row("Préfixe CIDR", f"/{network.prefixlen}")

    if network.version == 4:
        table.add_row("Masque (décimal)", str(network.netmask))
        table.add_row("Masque (binaire)", mask_to_binary(network))
        table.add_row("Adresse de broadcast", str(network.broadcast_address))
    else:
        table.add_row("Masque (binaire)", mask_to_binary(network))

    table.add_row("Première IP utilisable", str(first_usable))
    table.add_row("Dernière IP utilisable", str(last_usable))
    table.add_row("Nombre total d'hôtes", f"{total_hosts:,}".replace(",", " "))
    table.add_row("Type de l'adresse saisie", get_address_type(host_ip))

    console.print(table)


def display_error(message: str) -> None:
    """Affiche un message d'erreur dans un cadre rouge, clair et lisible."""
    console.print(Panel(f"[bold red]Erreur :[/bold red] {message}", border_style="red", title="Entrée invalide"))


def display_split_table(
    original: ipaddress.IPv4Network | ipaddress.IPv6Network,
    subnets: list,
) -> None:
    """Affiche un tableau listant chaque sous-réseau issu d'un découpage."""
    version_label = "IPv4" if original.version == 4 else "IPv6"

    table = Table(
        title=f"Découpage de {original} en {len(subnets)} sous-réseau(x) — {version_label}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("#", style="bold white", justify="right", no_wrap=True)
    table.add_column("Sous-réseau", style="green")
    table.add_column("Première IP utilisable", style="green")
    table.add_column("Dernière IP utilisable", style="green")
    if original.version == 4:
        table.add_column("Broadcast", style="green")
    table.add_column("Nb hôtes", style="green", justify="right")

    for index, subnet in enumerate(subnets, start=1):
        first_usable, last_usable, total_hosts = get_usable_hosts(subnet)
        row = [str(index), str(subnet), str(first_usable), str(last_usable)]
        if original.version == 4:
            row.append(str(subnet.broadcast_address))
        row.append(f"{total_hosts:,}".replace(",", " "))
        table.add_row(*row)

    console.print(table)


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #

def calculate_subnet(ip_input: str) -> None:
    """
    Point d'entrée du calcul : valide l'entrée utilisateur, construit l'objet
    réseau (ipaddress) et déclenche l'affichage des résultats.

    `strict=False` permet d'accepter une adresse d'hôte (ex: 192.168.1.45/24)
    sans lever d'exception, contrairement au mode strict qui exige une adresse
    réseau exacte (ex: 192.168.1.0/24).
    """
    try:
        interface = ipaddress.ip_interface(ip_input)
        network = interface.network
    except ValueError:
        display_error(
            "Le format saisi n'est pas une adresse IP/CIDR valide.\n"
            "Exemples attendus : 192.168.1.45/24  ou  2001:db8::/32"
        )
        return

    display_results(network, ip_input)


def run_batch(path, export_csv=None, export_json=None) -> None:
    """
    Lit une liste d'adresses IP/CIDR depuis un fichier texte (une par ligne,
    les lignes vides et celles commençant par '#' sont ignorées), calcule les
    résultats pour chacune, affiche un tableau récapitulatif, et exporte
    optionnellement les résultats en CSV/JSON.
    """
    file_path = Path(path)
    if not file_path.is_file():
        display_error(f"Le fichier « {path} » est introuvable.")
        return

    lines = [
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not lines:
        display_error(f"Le fichier « {path} » ne contient aucune adresse à traiter.")
        return

    rows = []
    table = Table(
        title=f"Résultats du traitement par lot — {len(lines)} adresse(s)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("Adresse saisie", style="bold white")
    table.add_column("Adresse réseau", style="green")
    table.add_column("Préfixe", style="green")
    table.add_column("Nb hôtes", style="green", justify="right")
    table.add_column("Type", style="green")

    for ip_input in lines:
        try:
            network = ipaddress.ip_interface(ip_input).network
        except ValueError:
            table.add_row(ip_input, "[red]Adresse invalide[/red]", "-", "-", "-")
            continue

        result = build_result_dict(network, ip_input)
        rows.append(result)
        table.add_row(
            result["Adresse saisie"],
            result["Adresse réseau"],
            result["Préfixe CIDR"],
            str(result["Nombre total d'hôtes"]),
            result["Type de l'adresse saisie"],
        )

    console.print(table)

    if rows:
        if export_csv:
            export_results_csv(rows, export_csv)
            console.print(f"[dim]Export CSV écrit dans {export_csv}[/dim]")
        if export_json:
            export_results_json(rows, export_json)
            console.print(f"[dim]Export JSON écrit dans {export_json}[/dim]")


def print_banner() -> None:
    """Affiche le titre d'accueil de l'application."""
    console.print(
        Panel(
            "[bold cyan]Calculateur de Sous-Réseaux IP[/bold cyan]\n"
            "[white]Compatible IPv4 & IPv6 — propulsé par le module Python `ipaddress`[/white]",
            border_style="cyan",
            box=box.DOUBLE,
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Calculateur de sous-réseaux IP (IPv4 & IPv6).",
    )
    parser.add_argument(
        "ip_cidr",
        nargs="?",
        help="Adresse IP/CIDR à analyser (ex: 192.168.1.45/24). Omis pour le mode interactif.",
    )
    parser.add_argument(
        "--split",
        type=int,
        metavar="N",
        help="Découpe le réseau en N sous-réseaux égaux.",
    )
    parser.add_argument(
        "--new-prefix",
        type=int,
        metavar="PREFIX",
        help="Découpe le réseau en utilisant ce nouveau préfixe (ex: 26).",
    )
    parser.add_argument(
        "--export-csv",
        metavar="FICHIER",
        help="Exporte le(s) résultat(s) au format CSV vers ce fichier.",
    )
    parser.add_argument(
        "--export-json",
        metavar="FICHIER",
        help="Exporte le(s) résultat(s) au format JSON vers ce fichier.",
    )
    parser.add_argument(
        "--batch",
        metavar="FICHIER",
        help="Traite une liste d'adresses IP/CIDR depuis un fichier texte (une par ligne).",
    )
    return parser


def main() -> None:
    """
    Boucle principale du programme.

    Modes d'utilisation :
      1. Argument direct : python subnet_calculator.py 192.168.1.45/24
      2. Découpage : python subnet_calculator.py 192.168.1.0/24 --split 4
      3. Export : python subnet_calculator.py 192.168.1.45/24 --export-csv resultats.csv
      4. Traitement par lot : python subnet_calculator.py --batch adresses.txt
      5. Mode interactif : python subnet_calculator.py (puis saisie manuelle)
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    print_banner()

    if args.batch:
        run_batch(args.batch, export_csv=args.export_csv, export_json=args.export_json)
        return

    if args.ip_cidr:
        try:
            network = ipaddress.ip_interface(args.ip_cidr).network
        except ValueError:
            display_error(
                "Le format saisi n'est pas une adresse IP/CIDR valide.\n"
                "Exemples attendus : 192.168.1.45/24  ou  2001:db8::/32"
            )
            return

        if args.split is not None or args.new_prefix is not None:
            try:
                subnets = split_network(network, num_subnets=args.split, new_prefix=args.new_prefix)
            except ValueError as error:
                display_error(str(error))
                return
            display_split_table(network, subnets)
            rows = [build_result_dict(subnet, str(subnet)) for subnet in subnets]
        else:
            display_results(network, args.ip_cidr)
            rows = [build_result_dict(network, args.ip_cidr)]

        if args.export_csv:
            export_results_csv(rows, args.export_csv)
            console.print(f"[dim]Export CSV écrit dans {args.export_csv}[/dim]")
        if args.export_json:
            export_results_json(rows, args.export_json)
            console.print(f"[dim]Export JSON écrit dans {args.export_json}[/dim]")
        return

    console.print("[bold]Entrez une adresse IP au format CIDR[/bold] (ex: [italic]192.168.1.45/24[/italic]).")
    console.print("[dim]Tapez 'quit' ou 'exit' pour quitter.[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]➜ Adresse IP/CIDR : [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Au revoir ![/dim]")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Au revoir ![/dim]")
            break

        if not user_input:
            continue

        calculate_subnet(user_input)
        console.print()  # ligne vide pour aérer l'affichage


if __name__ == "__main__":
    main()
